# Research: Action Gate (spec 011)

Each decision records what was chosen, why, and what else was considered. There are no open
NEEDS CLARIFICATION items.

**Revision 3 (option B, 2026-11-10)**: the gate lives in the agent runtime.
- Proposals are checked in the turn and saved at its end, within a deadline.
- Consent is handled in code only for an exact reply with a pending change in this chat.
- Rules live in policy modules.
- The `session_id` foreign key stays, and the back end's agent timeout becomes a setting.

Decisions from earlier revisions that no longer hold are listed under "Superseded".

## R1. Where the gate runs: in the agent runtime

**Decision**: The gate (`agent/src/wealth_agent/actions/`) runs in the AgentCore entrypoint's
process. Consent is handled before the model (R4) and proposals at the end of the turn (R3). State
is in the back end's Postgres (R6). The back end is a pass-through (R20).

**Rationale**: BL-037 names the agent runtime as the gate's layer, and BL-001 makes the runtime
validate the token. A gate in the runtime holds for every caller once the agent is hosted, not
only for traffic through this back end. Consent, the model turn and the conversation are in one
process, so the conversation can record each outcome (R19).

**Alternatives considered**: gate in the back end (revision 1; contradicts BL-037 and BL-001);
agent with its own store (second persistence pattern, no restart guarantees on a hosted runtime);
state through a new back-end API (extra endpoints and service authentication).

## R2. Identity: the agent verifies the participant's own token

**Decision**: The back end forwards the participant's bearer token unchanged in `Authorization`. The
agent verifies it with the rules of `backend/app/auth.py`: the same `OIDC_ISSUER`, `OIDC_AUDIENCE`
and `OIDC_JWKS_URL`; public-key algorithms only; the key from the key set; `exp`, `iss`, `aud` and
`sub` required; 60 s leeway; and the last-good key set kept while the key address is down. The
participant ID is `sub`. No ID is sent in any body.

- A missing, malformed or invalid token, or a key set that can't be fetched, means there is no
  participant for the turn. Actions are refused and chat works (BL-001 reading for this POC). The
  agent never returns 401.
- The token and claims are never logged, stored, traced or put in the conversation. Logs name only
  the failure reason.
- `bedrock_agentcore` 1.25.3 gives the entrypoint the header as
  `context.request_headers["Authorization"]`. An AgentCore inbound JWT authorizer added later
  forwards it the same way.

**Alternatives considered**: an ID in the body (anyone could act as anyone); a service token plus
an ID field (trusts the back end, not the participant); a 401 for the whole turn (stricter BL-001
reading, rejected for this POC by decision).

## R3. Turn 1: check in the tool, save at the end of the turn

**Decision**:
- `request_contribution_change(new_rate_pct)` first checks the argument is a finite number. If not,
  it returns `{ok: false, error}` so the model can correct itself.
- It then calls `gate.check_proposal(participant_id, session_id, action, allowed)`. This applies the
  policy's rules, reading the current rate through the contribution service, and writes nothing.
  - **Held**: the tool stores `{type, params}` in `agent.state["held_action"]` (the last held call in
    the turn wins) and returns `{ok: true, status: "held", note: "…the system will show the summary;
    do not say the change has been made"}`.
  - **Rejected**: it returns `{ok: true, status: "rejected", reason, message}`. `message` is the
    gate's plain sentence (for example "The contribution rate must be between 0% and 50%."), which
    the model uses to explain. It appends `{type, reason}` to `agent.state["rejected_actions"]`. No
    pending change is ever written for it.
- The tool gets the turn's participant, session and `allowed` flag from `agent.state["action_turn"]`,
  which `run_turn` sets before the model runs and removes afterwards. Without it (CLI, direct use),
  the tool returns `rejected` with reason `actions_unavailable`.
- **Turn memory isolation**: the turn memory (`action_turn`, `held_action`, `rejected_actions`)
  lives on the Strands agent that `agent_for` returns for one (participant, chat session) pair.
  `agent/agent.py` keys `_sessions` by that pair. A request without a verified participant runs on a
  fresh, empty agent that is not stored, so it keeps no conversation. Two participants, two chats or
  two token-less callers never share
  an agent or its state. `run_turn` clears the turn memory at the start of the turn and in a
  `finally` at the end.
- After the model has finished, `run_turn` pops `held_action` and `rejected_actions`. If either is
  present, it checks the elapsed time since the start of the turn against
  `ACTION_STAGE_DEADLINE_SECONDS` (R23). Within the deadline, one transaction writes a `rejected`
  audit row per rejected request (no `pending_action_id`) and, if a request is held, calls
  `gate.stage(...)`.

**Rationale**: the model can explain a rejection while writes happen only in code, after the model
has finished. A rejected request leaves an audit record but never a pending change.

**Alternatives considered**: Strands `invocation_state` for the turn context (needs `ask()` to pass
it, and `ask()` is in a PR #11 file); writing in the tool (writes before the deadline check and
before the model has finished); returning the request to the back end (revision 1).

## R4. Turn 2: every confirm or cancel message is handled in code; only an exact reply to a pending change in this chat runs anything

**Decision**: `classify(message)` runs first, on every message, and needs no identity or store.
Before the model runs, if it returns a `kind`, the first applicable case wins (spec FR-005):

| Case | Reply | Audit |
|---|---|---|
| 1. Actions disabled at start-up (missing OIDC or database settings, or deadline ≥ agent timeout) | "Contribution changes aren't available right now." | none; logged and traced (`actions_unavailable`) |
| 2. No verified participant (token missing, expired or invalid) | "Your sign-in has expired. Please sign in again, then reply confirm or cancel." | none; logged and traced with the case (`sign_in_token_missing`, `sign_in_token_expired` or `sign_in_token_invalid`; the code is `no_verified_participant` for the tool) |
| 3. `expire_overdue` or `find_pending` fails or times out | "Contribution changes aren't available right now." | none; logged and traced (`store_failed`) |

If none of cases 1 to 3 apply, with a verified participant and actions enabled (cases 4 to 8):
1. `gate.expire_overdue(participant)` marks this participant's overdue pending changes `expired`,
   each with an audit row.
2. `gate.find_pending(participant, session_id)` finds the unexpired pending change for this
   participant in this chat.
3. `classify(message)` normalises the message (trim, lower-case, strip . , ! ? ; : and quotes at both
   ends). It returns `(kind, exact)`:
   - `kind` is `confirm` or `cancel` when the message equals an accepted reply, or when its first
     word (with those marks stripped) is one;
   - `exact` is true only for the whole-message match;
   - `kind` is `None` otherwise. "confirmed" and "confirmation" aren't a match.
4. If `kind` is set, plain code replies and the model is not called. The first case that applies wins
   (spec FR-005):

   | Spec case | Reply | Audit |
   |---|---|---|
   | 4. Exact, pending here, actions allowed | confirm or cancel (below) | as the step |
   | 4. Exact, pending here, actions not allowed (education-only or no `ai_planning`) | the education-only refusal; stays pending | `rejected` (`education_only`) |
   | 5. Exact, the change here expired in step 1 | the gate's expired message | `expired` (already written in step 1) |
   | 6. Extra words, pending here | "Reply exactly confirm or cancel."; stays pending | `rejected` (`not_exact_reply`) |
   | 7. Nothing pending here, pending in another chat of this participant | "That change can only be confirmed in the chat where it was proposed." | `rejected` (`other_session`) |
   | 8. Nothing pending | "There is no change waiting for confirmation." | `rejected` (`nothing_pending`) |

5. Everything else, with no `kind`, goes to the model, which has no confirm or cancel tool. That
   includes, when actions can't run, every message that isn't a confirm or cancel message: it is
   answered normally and the tool refuses actions. None of them can run anything.

Turn 2 is linked to turn 1 only through the pending row in Postgres, looked up by `sub` and chat
session ID. "Confirm" carries no values; it runs exactly the staged row, once, before it expires.

**Rationale**: a message that starts with "confirm" or "cancel" is never left to the model to
interpret, so the model can't be talked into treating it as consent. The fixed replies tell the
participant exactly what to do. Only the exact reply to a known pending change in this chat runs
anything.

## R5. Confirmation token

**Decision**: Unchanged. On a valid confirm, the gate issues 32 random bytes from `secrets` and
stores only the SHA-256 hash.
- `ContributionService.apply_change(participant_id, new_rate_pct, token)` refuses a token issued to
  another participant or chat.
- It then redeems the token with one conditional update: hash matches, unused, not expired, marked
  used.
- The token never leaves the agent process and never enters the conversation.

## R6. Persistence: the back end's Postgres, schema through the back end's Alembic

**Decision**:
- **Schema**: migration 0005 and `backend/app/models.py` own `contributions`, `pending_actions` and
  `action_audit`. That includes the foreign key `pending_actions.session_id → sessions.id`, which is
  kept. The agent never creates or alters tables.
- **Session row first**: the back end creates the `sessions` row (owner check, retry once on
  `IntegrityError`) and commits it before calling the agent. The FK therefore holds when the agent
  stages on a new chat's first message (R20).
- **Agent access**: `store.py` defines the three tables (and a minimal `sessions` table for the FK)
  with SQLAlchemy 2 (sync) and builds a lazy engine from `DATABASE_URL` (psycopg 3). Without
  `DATABASE_URL`, actions are disabled at start-up (R16).
- **Statement timeout**: every gate statement, reads included, runs in a transaction that starts with
  `SET LOCAL statement_timeout` set to `ACTION_DB_TIMEOUT_SECONDS` (default 3) on Postgres. A timeout
  or any database error rolls the step back: nothing is staged or run. A read that fails or times
  out before the model runs (expiry, pending lookup) gives the "isn't available right now" reply
  for a confirm or cancel message (R4); for any other message the turn continues to the model with
  actions refused. Either way the failure is logged and traced, not recorded.
- **Transactions**: each gate step is one agent transaction. The approved follow-up transactions
  remain (failed apply, step-up refusal). The back end stores the messages in its own transaction
  afterwards (approved split).
- **Drift guard**: R21.

## R7. Expiry

**Decision**: `expires_at = staged_at + ACTION_EXPIRY_SECONDS` (default 300). On every turn with a
verified participant, `expire_overdue` marks overdue pending changes `expired`, with audit rows,
before anything else. `find_pending` and `redeem` also ignore or refuse expired rows. Tests inject
a clock.

## R8. Concurrency

**Decision**:
- **Two confirms for the same change**: a conditional update `pending → confirmed` decides; the
  loser gets `already_handled`.
- **Two proposals that race**: they hit the partial unique index. `stage` retries once in a new
  transaction, and the retry replaces the pending row it finds.

## R9. Message `source` for gate replies

**Decision**: The agent's response gains an optional `source`, `"gate"` when the gate wrote the reply.
The back end stores `gate`, `agent` or `mock`; `latency_ms` is kept for gate replies. The history and
front-end types include `gate` (US1). Turn-1 rejection explanations are model text, so they are
stored as `agent`.

## R10. Footer and disclaimer

**Decision**: Gate messages end with "Demo data: no real account was changed." (one helper) and don't
get spec 005's disclaimer. Model replies get the disclaimer from `ask()` and never the footer. The
copies kept in the conversation omit the footer.

## R11. GR-ACTION-GATE tracing, independent of PR #11

**Decision**: `actions/tracing.py`, `emit_gate_outcome(step, reason, action_type)`, adds a
`guardrail.check` event with PR #11's attributes:

| Attribute | Value |
|---|---|
| `guardrail_rule_id` | `GR-ACTION-GATE` |
| `guardrail_result` | `pass` for held, staged, confirmed, cancelled and executed; `fail` for rejected, expired, failed and too_slow |
| `guardrail_reason` | the reason code |
| `guardrail_action` | `allow` or `block` |
| `action.type`, `action.step` | for example `contribution_change` and `staged` |

The event goes on the current recording span, or on a short span of its own,
`wealth_agent.action_gate`. It also covers outcomes that are not audited (`actions_unavailable`, `sign_in_token_missing`, `sign_in_token_expired`, `sign_in_token_invalid`,
`too_slow`, `store_failed`). It is called after commit, inside `try/except`. No participant ID is sent. It is
visible once PR #11 is merged and tracing is on, and is a no-op otherwise.

## R12. The audit record is authoritative for gate steps

**Decision**: `action_audit` is the record of every gate step: `staged`, `cancelled`
(`participant_cancelled` or `replaced`), `confirmed`, `executed`, `failed`, `expired`, and
`rejected`. `rejected` covers three cases:
- turn-1 rule rejections, written at the end of the turn with no `pending_action_id`;
- consent-turn refusals (`education_only`, `already_handled`, `stale`, `step_up_required`,
  `token_invalid`);
- the fixed replies (`not_exact_reply`, `other_session`, `nothing_pending`).

How rows are written:
- Each row is written in the same transaction as the state change, and rows are only ever inserted.
- Each row holds the participant ID, time, action type, staged-change ID, step and reason, and
  nothing else.
- Logged and traced but not recorded (accepted): turns without a verified participant (including
  the sign-in reply), turns with actions disabled or an unreadable store (including their fixed
  replies), turns past the staging deadline (including their rejected requests), and failed saves.
- If the back end later fails to store the gate's chat message, state and audit remain correct and
  are the authority (data-model.md).

The step `proposed` is removed; `staged` is the first recorded step, and the audit never claims a
summary was "shown to the participant".

## R13. Step-up hook

**Decision**: `StepUpCheck.verify(participant_id, action_type, claims) -> bool`, with the verified
claims. It is passed to `run_turn` (default `AlwaysPass`). On refusal the change rolls back and the
follow-up writes `confirmed` and `rejected` (`step_up_required`); the change stays pending.

## R14. Demo payroll seed

**Decision**: `agent/src/wealth_agent/data/payroll.json`, loaded once by `contribution_service.py`. If
the file is missing or invalid, the policy check returns `seed_unavailable` to the model.
`portfolio.json` is untouched.

## R15. Money arithmetic

**Decision**: Unchanged: `Decimal` values, computed from exact amounts and rounded half-up to cents
(FR-019). The figures are in `contribution_policy.py`.

## R16. Settings and the start-up check

| Variable | Read by | Default |
|---|---|---|
| `AGENT_TIMEOUT_SECONDS` | back end (HTTP timeout) and agent (start-up check) | `60` |
| `ACTION_STAGE_DEADLINE_SECONDS` | agent | `50` |
| `ACTION_DB_TIMEOUT_SECONDS` | agent | `3` |
| `ACTION_EXPIRY_SECONDS` | agent | `300` |
| `ACTION_CONFIRM_REPLIES` / `ACTION_CANCEL_REPLIES` | agent | `confirm` / `cancel` |
| `CONTRIBUTION_MIN_PCT` / `CONTRIBUTION_MAX_PCT` | agent | `0` / `50` |
| `DATABASE_URL`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` | agent (new) and back end | none |

`CONTRIBUTION_WHOLE_PCT_ONLY` is removed: whole percentages are a fixed rule.

**Start-up check** (`config.startup_check()`, called once when `agent/agent.py` is imported):
actions are disabled when any of `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` or `DATABASE_URL`
is missing, or when `ACTION_STAGE_DEADLINE_SECONDS` is not lower than `AGENT_TIMEOUT_SECONDS`. One
warning names every problem. Chat is unaffected.

## R17. Open pull requests

- **PR #11** (tracing, still specs only) plans changes to `agent/agent.py` (configure tracing; pass
  `session_id` to `ask()`), `agent/src/wealth_agent/agent.py`, `tools.py`, `test_agent.py`,
  `test_tools.py`, `requirements.txt`, `pyproject.toml` and `README.md`.
  - Expected conflicts: the `invoke` body and signature in `agent/agent.py`, and the dependency lines
    in `requirements.txt` and `pyproject.toml`.
  - Kept small by putting logic in `turn.py`, passing `ask` as a callable, and putting the turn
    context on `agent.state`, so `ask()` doesn't change.
  - Noted in the PR description (plan.md).
- **PR #8** (merged into `009-sign-in-access-backend`, not `main`): `README.md`, `.env.example` and
  `frontend/packages/core/src/api.ts`.
- PRs #9 and #10 share no files.

## R18. Entitlement in the agent

**Decision**: Actions need a verified participant, `ai_planning` exactly `true`, and no
`education_only: true` in the request. The deny list and `ENTITLEMENT_MODE` stay in the back end.
- Turn-1 refusals return to the model as `rejected`: `education_only` (recorded at the end of the
  turn) or `no_verified_participant` (logged and traced only).
- A turn-2 refusal of an exact reply with a pending change is recorded (`education_only`).

## R19. Gate outcomes join the agent's conversation

**Decision**: See plan.md "Conversation update".
- Staged and try-again texts replace the model's final assistant text.
- Consent outcomes and the fixed replies are appended as a user and assistant pair.
- An expiry noticed on another turn adds a short note to the last assistant message.
- Turn-1 rejections are already in the conversation through the tool result.

The footer and the token are never included. The eval `contribution-now-after-confirm` checks the
result. The conversation is in-process and lost on restart (BL-012).

## R20. The back end as a pass-through

**Decision**: `POST /api/chat`:
1. Existing checks (400, 401, 404, 403).
2. `_ensure_session` creates and commits the session row if it is new.
3. `call_agent` with the token in `Authorization`, `prompt`, `session_id` and `education_only` when
   true, timeout `AGENT_TIMEOUT_SECONDS` (default 60).
4. Store the messages with `source` `gate`, `agent` or `mock`.

The back end doesn't read the gate tables. The raw token comes from `auth.verified_token`, after
`verified_claims` has accepted it, and is never logged.

**Consequence**: the new-session ownership race now happens before the agent call. The existing test
`test_two_users_racing_for_one_new_session_id` is adapted: the second creator gets 404 and the
agent is not called.

## R21. Keeping two definitions of the tables in step

**Decision**: `backend/tests/test_agent_store_schema.py` loads the agent's `store.py` by path (it
imports only SQLAlchemy). It compares table and column names, types, nullability, check constraints,
the FK and the partial unique index with `backend/app/models.py`. `agent/tests/test_identity.py`
mirrors the token cases of `backend/tests/test_auth.py`.

## R22. New agent runtime dependencies (approved)

**Decision**: `sqlalchemy>=2,<3`, `psycopg[binary]>=3,<4` and `pyjwt[crypto]>=2.10,<3`, in
`agent/requirements.txt` and `agent/pyproject.toml`. These match the back end's entries.

## R23. Timing

**Decision**:
- **Deadline**: `run_turn` makes its end-of-turn writes (staging, and `rejected` rows) only if
  `monotonic() - t0 < ACTION_STAGE_DEADLINE_SECONDS`, where `t0` is taken on entry. Otherwise
  nothing is written (`too_slow`, logged and traced). If a request was held, the reply is the
  gate's "try again" text. If the turn only had rejected requests, the model's explanation is kept,
  because it is still accurate.
- **Database**: gate statements are limited by `ACTION_DB_TIMEOUT_SECONDS` (R6). A timeout or error
  in the end-of-turn transaction writes nothing (`store_failed`). The reply is "try again" if a
  request was held; otherwise the model's explanation is kept. During confirm, it rolls back, the
  change stays pending, and the reply asks to try again. If writing a fixed reply's `rejected` row
  fails, the fixed reply is still sent (`store_failed`, logged and traced).
- **Back end**: `AGENT_TIMEOUT_SECONDS` (default 60) replaces the hard-coded 10 s. With the defaults,
  a staged change is committed by about 53 s, inside the 60 s wait.
- **Agent down**: the back end's mock reply. A "confirm" or "cancel" gets it too, and the pending
  change expires (accepted behaviour change).

## R24. Tests: ported, not rewritten

| Revision 1 test | Revision 3 test | Change |
|---|---|---|
| `backend/tests/test_contribution.py` | `agent/tests/test_contribution_policy.py` and `test_contribution_service.py` | Split by module; whole-only setting case removed |
| `backend/tests/test_action_support.py` | `agent/tests/test_action_config.py` and `test_action_support.py` | Settings vs helpers; whole-only cases removed |
| `backend/tests/test_action_gate.py` | `agent/tests/test_action_gate.py` | `say()` calls `run_turn` with signed tokens; the scripted model calls the tool; assertions on reply, rate, pending rows and audit kept, except: refused proposals return the reason to the model, and the reply is model text, while the `rejected` row is still written (at the end of the turn, no `pending_action_id`); the `nothing_pending` reply text changes to "There is no change waiting for confirmation."; the audit no longer has `proposed` |
| `agent/tests/test_action_tools.py` | same | The tool's result is `held` or `rejected` with the reason; state cases kept |
| `agent/tests/test_entrypoint.py` | same | The `action` cases become `source: gate` cases |
| `backend/tests/test_agent.py` (action parsing, 10 s timeout) | same | Token header, `source` parsing, timeout from the environment (default 60) |
| `backend/tests/test_action_models.py`, `test_action_migration.py` | stay | Step check without `proposed` |

New tests are listed in tasks.md. They include every test in the request: deadline, failed or
timed-out write, rejection to the model, confirm from another participant, chat, after expiry or
with extra text, "skip confirmation", missing or invalid token, and the turn-2 eval.

## R25. Policy modules

**Decision**: `gate.py` holds only the generic flow: check, stage, find, confirm, cancel, expire,
token, audit, footer. Each action supplies an `ActionPolicy` in `actions/policies/<name>_policy.py`,
with `parse`, `check`, `summary`, `execute` and optionally `cancel_message`. It is registered in
`actions/policies/__init__.py` as `POLICIES[name] = builder`.
- `contribution_policy.py` holds: range 0–50 (settings), whole percentages (fixed), different from
  the current rate, the dollar figures and the match warning.
- `contribution_service.py` is the single replaceable data source (get current rate; apply a change
  with a token).

A new action adds a policy module and one registry line, and the gate doesn't change.

## Superseded

- Revision 1: gate in the back end; no participant ID to the agent; classification in `POST /api/chat`; everything in `_persist`'s one transaction; the `action` response field; seed in `backend/app/data/`.
- Revision 2: proposals staged inside the turn; no FK on `pending_actions.session_id`; the step `proposed`; the hard-coded 10 s timeout.
- Revision 3 first draft (replaced after the spec owner's review): turn-1 rejections not audited, and "confirm" or "cancel" messages without an exact pending match sent to the model.
