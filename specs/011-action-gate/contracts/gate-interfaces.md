# Contract: Gate interfaces (spec 011, internal to the agent runtime, revision 3)

These are the seams that must hold as the POC grows: new actions, a real contribution source,
step-up authentication (method still to be decided) and a hosted runtime. They are Python
protocols and functions in `agent/src/wealth_agent/actions/`. The signatures are the contract; the
bodies are not. Nothing here imports FastAPI or the back end.

## Package layout

| Module | Holds |
|---|---|
| `config.py` | `GateSettings` (all settings in research R16), `startup_check()` → `ActionsStatus(enabled, problems)`, one warning |
| `identity.py` | `verify_participant` |
| `store.py` | Table definitions mirroring `backend/app/models.py`; lazy engine from `DATABASE_URL`; `transaction()` with the statement timeout |
| `gate.py` | Generic flow only: `ActionGate`, `GateRefusal`, `CheckResult`, `GateResult`, `ConfirmationToken`, `ActionPolicy` and `StepUpCheck` protocols, footer helper, audit helper, token issue and redeem |
| `policies/__init__.py` | `POLICIES: dict[str, PolicyFactory]` |
| `policies/contribution_policy.py` | `ContributionPolicy`: rules, figures, match warning, texts |
| `contribution_service.py` | `ContributionService` protocol, `DemoContributionService`, payroll seed loader |
| `tracing.py` | `emit_gate_outcome` |
| `turn.py` | `run_turn` |

## `startup_check` (FR-016a, FR-033)

```python
@dataclass(frozen=True)
class ActionsStatus:
    enabled: bool
    problems: tuple[str, ...]   # e.g. ("OIDC_JWKS_URL is not set", "ACTION_STAGE_DEADLINE_SECONDS (60) must be lower than AGENT_TIMEOUT_SECONDS (60)")

def startup_check(env=os.environ) -> ActionsStatus: ...   # logs one warning listing every problem
```

`AGENT_TIMEOUT_SECONDS` is read from the same environment variable the back end reads, with the same
default (60). The plan says where each process gets it (plan.md "Where `AGENT_TIMEOUT_SECONDS` comes from").

## `verify_participant` (FR-014 to FR-016)

```python
@dataclass(frozen=True)
class Participant:
    id: str        # the verified token's sub
    claims: dict   # for ai_planning and StepUpCheck; never logged or stored

SignInFailure = Literal["sign_in_token_missing", "sign_in_token_expired", "sign_in_token_invalid"]

@dataclass(frozen=True)
class Verification:
    participant: Participant | None
    failure: SignInFailure | None    # set exactly when participant is None

def verify_participant(authorization: str | None) -> Verification: ...
```

It uses the rules of `backend/app/auth.py`. It never raises and never logs the token. The failure is:
- `sign_in_token_missing`: no `Authorization` header, an empty one, or one that isn't `Bearer <token>`;
- `sign_in_token_expired`: the token's `exp` has passed, beyond the 60 s leeway;
- `sign_in_token_invalid`: anything else (bad signature, wrong issuer or audience, disallowed
  algorithm, missing `sub`, malformed token, unreachable key set with no cached keys).

`run_turn` logs the failure name with the sign-in reply and the trace (`guardrail_reason`), never the token.
The audit's `token_invalid` reason is a different thing: a confirmation token refused by `apply_change`.

## `ActionPolicy` (one module per action; FR-002)

```python
class ActionPolicy(Protocol):
    name: str
    def parse(self, params: dict) -> dict: ...            # GateRefusal("invalid_params")
    def check(self, participant_id: str, params: dict) -> dict: ...
        # GateRefusal(reason, message) or the snapshot for the summary; reads only
    def summary(self, params: dict, snapshot: dict, expiry_minutes: int) -> str: ...
    def execute(self, participant_id: str, params: dict, snapshot: dict,
                token: ConfirmationToken) -> str: ...
    # optional: def cancel_message(self, snapshot: dict) -> str

PolicyFactory = Callable[[PolicyContext], ActionPolicy]   # PolicyContext: db, settings, contributions
POLICIES: dict[str, PolicyFactory]                        # in actions/policies/__init__.py
```

A new action adds `actions/policies/<name>_policy.py` and one line in `POLICIES`; `gate.py` doesn't
change. `ContributionPolicy` holds: range `CONTRIBUTION_MIN_PCT`–`CONTRIBUTION_MAX_PCT` (0–50),
whole percentages (fixed), different from the current rate, the dollar figures and the match warning.

## `ContributionService` (FR-021)

```python
class ContributionService(Protocol):
    def current_rate(self, participant_id: str) -> int: ...
    def apply_change(self, participant_id: str, new_rate_pct: int,
                     token: ConfirmationToken) -> int: ...
```

`DemoContributionService(db, seed=None, redeem=None)` reads `contributions` and falls back to the seed.
`apply_change` refuses a token for another participant or chat, redeems it once (refusing an
expired one), then upserts. It is chosen through `run_turn(..., contributions_for=...)`. A future
`PrincipalContributionService` keeps the two methods and sends `token.pending_action_id` as the
idempotency key.

## `StepUpCheck` (FR-012)

```python
class StepUpCheck(Protocol):
    def verify(self, participant_id: str, action_type: str, claims: dict) -> bool: ...
```

The default is `AlwaysPass`, passed through `run_turn(..., step_up=...)`.

## `ActionGate` (generic flow)

```python
class ActionGate:   # ActionGate(store, settings, contributions_for, step_up, clock)
    def check_proposal(self, participant_id, session_id, action: dict, allowed: bool) -> CheckResult: ...
        # read-only: held or rejected(reason, message)
    def stage(self, participant_id, session_id, action: dict) -> GateResult: ...
        # one transaction: re-check, replace an older pending (cancelled, replaced), insert, audit "staged"
    def record_rejections(self, participant_id, rejected: list[dict]) -> None: ...
        # end of turn, same transaction as stage when both happen; step "rejected", no pending_action_id
    def expire_overdue(self, participant_id, session_id) -> list[GateResult]: ...
    def find_pending(self, participant_id, session_id) -> PendingRef | None: ...   # unexpired, this chat
    def find_pending_elsewhere(self, participant_id, session_id) -> PendingRef | None: ...   # another chat
    def classify(self, message: str) -> Reply | None: ...
        # Reply(kind: "confirm" | "cancel", exact: bool); first word or whole message, FR-005 normalisation
    def confirm(self, participant: Participant, pending: PendingRef, allowed: bool) -> GateResult: ...
    def cancel(self, participant: Participant, pending: PendingRef, allowed: bool) -> GateResult: ...
    def refuse_reply(self, participant_id, reason: str, pending: PendingRef | None) -> GateResult: ...
        # not_exact_reply, other_session, nothing_pending: fixed text, audit "rejected"
```

- Every write runs in `store.transaction()`, with `ACTION_DB_TIMEOUT_SECONDS` as the statement
  timeout. A timeout or database error raises `GateStoreError`. `run_turn` turns it into the
  "try again" reply, and nothing is staged or run.
- The gate never commits itself, except the two approved follow-ups (failed apply, step-up refusal).

## Tool ↔ gate (turn memory)

- `run_turn` sets `agent.state["action_turn"] = {"participant_id", "session_id", "allowed"}` before
  the model runs, and removes it afterwards.
- `request_contribution_change` calls `gate.check_proposal(...)`. On `held` it sets
  `agent.state["held_action"]` (the last held call wins). On `rejected` it appends `{type, reason}` to
  `agent.state["rejected_actions"]`. It never writes to the database.
- Without `action_turn`, the tool returns `rejected` (`actions_unavailable`), which isn't recorded.
- The turn memory belongs to the agent for one (participant, chat session) pair and is cleared at the
  start of `run_turn` and in its `finally` (spec FR-017).

## `run_turn` (called by `agent/agent.py`)

```python
def run_turn(payload: dict, authorization: str | None, *,
             agent_for: Callable[[str | None, str], Agent],   # None participant: fresh, empty, not stored
             ask: Callable[[Agent, str], str],
             gate: ActionGate | None = None,
             status: ActionsStatus | None = None,
             monotonic=time.monotonic) -> dict: ...
    # {"reply", "intent"} or {"reply", "intent", "source": "gate"}
```

The order is: verify; expire; confirm and cancel replies in code; model turn with turn context;
deadline; end-of-turn writes (rejections and staging); conversation update; trace. See plan.md "Agent: one turn". `ask` is passed in so that PR #11's
`ask(agent, text, session_id=...)` threads through unchanged.

## GR-ACTION-GATE trace event (optional; independent of PR #11)

See research R11. It goes on the current span or on its own `wealth_agent.action_gate` span, covers
unrecorded outcomes too, and never carries the participant ID, rates or chat text.
