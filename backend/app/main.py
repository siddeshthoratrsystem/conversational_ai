import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import feedback, models
from app import auth
from app.auth import current_user, verified_claims, verified_token
from app.agent import AgentError, call_agent, log_timeout_at_start_up
from app.entitlement import check_access
from app.db import get_db

logging.basicConfig(format="%(levelname)s [%(name)s] %(message)s")  # show the level on app logs
logger = logging.getLogger("app.chat")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    auth.load_settings()  # refuse to start, naming the setting, if the sign-in check isn't configured
    log_timeout_at_start_up()  # which AGENT_TIMEOUT_SECONDS this process uses (spec 011)
    yield


app = FastAPI(title="Conversational AI backend", lifespan=lifespan)
app.include_router(feedback.router)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    intent: str | None = None
    # Id of the assistant message created for this reply (the id to rate). Typed nullable because
    # new fields must be nullable or optional (Principle I), but always an integer today.
    message_id: int | None
    # Spec 009: present (true) only when the access check could not be completed and only
    # education is offered; left out otherwise, so existing replies are unchanged.
    education_only: bool | None = None


class HistoryMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    intent: str | None
    latency_ms: int | None
    source: Literal["agent", "mock", "gate"] | None
    created_at: datetime


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    last_active_at: datetime


class SessionsResponse(BaseModel):
    sessions: list[SessionSummary]


class MeResponse(BaseModel):
    user_id: str
    name: str
    access: Literal["granted", "denied", "unavailable"]


MAX_SESSION_IDS = 200
TITLE_MAX_CHARS = 80


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _reply_for(session_id: str, message: str, education_only: bool = False, token: str | None = None) -> dict:
    """Ask the agent; fall back to the mock reply (and log why) if it is unset or fails."""
    agent_url = os.getenv("AGENT_URL")  # full URL, e.g. http://localhost:8080/invocations
    if not agent_url:
        logger.warning("AGENT_URL is not set; returning mock reply (session_id=%s)", session_id)
    else:
        try:
            # Pass the flag only when set, so the agent call is unchanged otherwise.
            extra = {"education_only": True} if education_only else {}
            result = call_agent(agent_url, session_id, message, token=token, **extra)
            return {
                "reply": result.reply,
                "intent": result.intent,
                "latency_ms": result.latency_ms,
                # Spec 011: "gate" when the agent wrote the text in code; anything else is "agent".
                "source": "gate" if result.source == "gate" else "agent",
            }
        except AgentError as e:
            logger.warning(
                "Agent call failed (%s); returning mock reply (session_id=%s)", e, session_id
            )
    return {
        "reply": f"(mock) You said: {message}",
        "intent": None,
        "latency_ms": None,
        "source": "mock",
    }


SESSION_NOT_FOUND = "session not found"


def _refuse_session(db: DbSession, session_id: str, user_id: str) -> HTTPException:
    """The one 404 for a chat that is missing, someone else's or nobody's (FR-017).

    The response is identical in every case; only the log says which one it was.
    """
    row = db.get(models.Session, session_id)
    case = "missing" if row is None else "nobody's" if row.user_id is None else "someone else's"
    logger.warning("Session refused (404): %s is %s (session_id=%s)", case, case, session_id)
    return HTTPException(status_code=404, detail=SESSION_NOT_FOUND)


def _check_owner(db: DbSession, session_id: str, user_id: str) -> bool:
    """True if the session exists and is the caller's. Raises 404 if it exists but is not."""
    row = db.get(models.Session, session_id)
    if row is None:
        return False
    if row.user_id != user_id:
        raise _refuse_session(db, session_id, user_id)
    return True


def _ensure_session(db: DbSession, session_id: str, user_id: str, access: str) -> None:
    """Make sure the caller's chat row exists and is committed before the agent is called (spec 011).

    The agent's gate has a foreign key to the session, so the row must exist first. A chat that is
    someone else's or nobody's is the usual 404. If another request creates the same new id at the
    same moment, retry once; the retry sees the other owner and answers 404 (research R20).
    """
    for attempt in (1, 2):
        try:
            if _check_owner(db, session_id, user_id):
                return
            db.add(
                models.Session(
                    id=session_id,
                    user_id=user_id,
                    access=access,
                    access_checked_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND) from None
        except HTTPException:
            db.rollback()
            raise


def _persist(
    db: DbSession,
    session_id: str,
    user_id: str,
    message: str,
    result: dict,
    access: str,
) -> int:
    """Store the session (if new) plus the user and assistant messages in one transaction, and
    record this turn's access result on the session (spec 009).

    A new session is owned by the caller. If another user's session turned up meanwhile, the
    answer is the same 404 and nothing is stored. Returns the id of the assistant message.
    """
    for attempt in (1, 2):
        try:
            checked_at = datetime.now(timezone.utc)
            if not _check_owner(db, session_id, user_id):
                db.add(models.Session(id=session_id, user_id=user_id, access=access, access_checked_at=checked_at))
                # No relationship() links the models, so the unit of work won't order the inserts
                # by FK; flush the session row first (still the same transaction).
                db.flush()
            else:
                session = db.get(models.Session, session_id)
                session.access, session.access_checked_at = access, checked_at
            db.add(models.Message(session_id=session_id, role="user", content=message))
            assistant = models.Message(
                session_id=session_id,
                role="assistant",
                content=result["reply"],
                intent=result["intent"],
                latency_ms=result["latency_ms"],
                source=result["source"],
            )
            db.add(assistant)
            db.flush()  # assigns the id; read it before commit, which expires the object
            assistant_id = assistant.id
            db.commit()
            return assistant_id
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            # Lost a race creating the same new session concurrently; retry once (the retry
            # re-checks the owner, so a different user's session id is a 404).
            db.rollback()
            if attempt == 2:
                raise


@app.get("/api/me", response_model=MeResponse)
def me(claims: dict[str, Any] = Depends(verified_claims)):
    """Who is signed in and what they may use (spec 009)."""
    name = claims.get("name") or claims.get("preferred_username") or claims["sub"]
    return MeResponse(user_id=claims["sub"], name=name, access=check_access(claims))


@app.post("/api/chat", response_model=ChatResponse, response_model_exclude_unset=True)
def chat(
    req: ChatRequest,
    user_id: str = Depends(current_user),
    claims: dict[str, Any] = Depends(verified_claims),
    token: str = Depends(verified_token),
    db: DbSession = Depends(get_db),
):
    if not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id must not be empty")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    # Someone else's (or nobody's) session is a 404 before anything else happens.
    _check_owner(db, req.session_id, user_id)

    # Spec 009: no AI planning without access; education only when access can't be decided.
    access = check_access(claims)
    if access == "denied":
        logger.warning("AI planning refused (403) (user_id=%s, session_id=%s)", user_id, req.session_id)
        raise HTTPException(status_code=403, detail="AI planning is not available for this account")
    education_only = access == "unavailable"

    # A new chat's row is committed now, so the agent's gate can refer to it (spec 011). The owner
    # is checked again here, because another request may have created the same id meanwhile.
    _ensure_session(db, req.session_id, user_id, access)
    db.rollback()  # end the read transaction so no connection is held during the agent call

    # The agent is called before writing so no transaction is held open during the HTTP call;
    # both messages are still written and committed together afterwards. The participant's own
    # token goes with the call: the agent verifies it and runs the action gate (spec 011).
    result = _reply_for(req.session_id, req.message, education_only, token)
    message_id = _persist(db, req.session_id, user_id, req.message, result, access)
    extra = {"education_only": True} if education_only else {}
    return ChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        intent=result["intent"],
        message_id=message_id,
        **extra,
    )


@app.get("/api/chat/{session_id}/history", response_model=HistoryResponse)
def history(
    session_id: str, user_id: str = Depends(current_user), db: DbSession = Depends(get_db)
):
    if not _check_owner(db, session_id, user_id):
        raise _refuse_session(db, session_id, user_id)
    rows = db.scalars(
        select(models.Message)
        .where(models.Message.session_id == session_id)
        .order_by(models.Message.created_at, models.Message.id)
    ).all()
    return HistoryResponse(session_id=session_id, messages=rows)


def _title_from(message: str) -> str:
    """First user message as a one-line label: collapse whitespace, cap at 80 chars plus '…'."""
    text = " ".join(message.split())
    return text if len(text) <= TITLE_MAX_CHARS else text[:TITLE_MAX_CHARS] + "…"


@app.get("/api/sessions", response_model=SessionsResponse)
def list_sessions(
    ids: list[str] = Query(default=[]),
    user_id: str = Depends(current_user),
    db: DbSession = Depends(get_db),
):
    """Summaries of the requested sessions (the browser's own list), newest activity first.

    Read-only: unknown ids are skipped and nothing is created.
    """
    if len(ids) > MAX_SESSION_IDS:
        raise HTTPException(status_code=400, detail=f"too many session ids (max {MAX_SESSION_IDS})")
    wanted = {i.strip() for i in ids if i.strip()}
    if not wanted:
        return SessionsResponse(sessions=[])

    msg = models.Message
    first_user_message = (
        select(msg.content)
        .where(msg.session_id == models.Session.id, msg.role == "user")
        .order_by(msg.created_at, msg.id)
        .limit(1)
        .correlate(models.Session)
        .scalar_subquery()
    )
    last_active = func.max(msg.created_at).label("last_active_at")
    rows = db.execute(
        select(models.Session.id, models.Session.created_at, last_active, first_user_message.label("title"))
        .join(msg, msg.session_id == models.Session.id)
        .where(models.Session.id.in_(wanted), models.Session.user_id == user_id)
        .group_by(models.Session.id, models.Session.created_at)
        .order_by(last_active.desc(), models.Session.id)
    ).all()

    return SessionsResponse(
        sessions=[
            SessionSummary(
                session_id=r.id,
                title=_title_from(r.title or ""),
                created_at=r.created_at,
                last_active_at=r.last_active_at,
            )
            for r in rows
        ]
    )
