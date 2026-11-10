---

description: "Task list for spec 011 revision 3: action gate in the agent runtime (mock 401(k) contribution change)"
---

# Tasks: Action Gate for Agent Write Actions (Mock 401(k) Contribution Change), revision 3

**Input**: Design documents from `/specs/011-action-gate/`

**Prerequisites**: plan.md (revision 3), spec.md, research.md (R1–R25), data-model.md, contracts/agent-api.md, contracts/backend-api.md, contracts/gate-interfaces.md, quickstart.md

**Tests**: Required (constitution IV, FR-030). In every phase, the test tasks come first and each test MUST be run and seen to fail before the implementation tasks that follow it. Existing back-end, agent and front-end tests must keep passing.

**Starting point**: the revision 1 US1 work (old T001–T031) is in the working tree, uncommitted. These tasks move it into the agent, port its tests and revert the back-end gate wiring (plan.md "What happens to the US1 work"). "Port" means `git mv` the file, then edit imports, fixtures and only the expectations that revision 3 changes. Don't rewrite passing cases.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 to US4, from spec.md
- All paths are relative to the repository root

## Rules for every task

- Run back-end tests with `cd backend && pytest` and agent tests with `cd agent && pytest`. Neither needs Postgres, Ollama, an identity provider or a network.
- Do not edit: `agent/src/wealth_agent/data/portfolio.json`, `agent/tests/test_portfolio.py`, `specs/005-*`, `agent/src/wealth_agent/tools.py`, `agent/tests/test_tools.py`, `docker-compose.yml`, `backend/tests/conftest.py`.
- Files flagged **[PR #11]** (`agent/agent.py`, `agent/src/wealth_agent/agent.py`, `agent/tests/test_agent.py`, `agent/requirements.txt`, `agent/pyproject.toml`, `README.md`): keep each diff as small as the task allows. Nothing may import or depend on PR #11. OpenTelemetry is imported only inside `agent/src/wealth_agent/actions/tracing.py`, guarded.
- Bearer tokens and claims are never logged, stored, traced or put in the agent's conversation. Tests assert it wherever a token is handled.
- The audit holds only `user_id`, `action_type`, `pending_action_id`, `step`, `reason` and `created_at` (FR-025). No chat text, rates, names or salary.
- Every message written by the gate ends with the footer line `Demo data: no real account was changed.`, added by one helper. No model reply gets it, and the copy added to the conversation omits it (FR-031).
- Extra transactions are allowed only for the approved cases (plan.md Complexity Tracking): the follow-up that records a failed apply or a step-up refusal, and the back end committing the session row before the agent call.
- Every gate statement, reads included, runs inside `store.transaction()` with the `ACTION_DB_TIMEOUT_SECONDS` limit.
- Agent gate tests use the fixtures in `agent/tests/conftest.py` (T016): signed tokens, a fake key client, an in-memory SQLite store with a failure switch, the scripted model, an injected clock and an injected `monotonic`.

---

## Phase 1: Setup

- [ ] T001 Run `cd backend && pytest`, `cd agent && pytest` and `cd frontend && npm test` on the current working tree (revision 1 US1 uncommitted) and note the result as the baseline (paths: `backend/tests/`, `agent/tests/`, `frontend/`)
- [ ] T002 Amend `.specify/memory/constitution.md` with `/speckit-constitution`. In Principle II, the `source` rule becomes "`agent`, `mock` or `gate`", and "Outbound agent calls MUST have an explicit timeout (currently 10s)" becomes "configurable through `AGENT_TIMEOUT_SECONDS`, default 60 seconds". Bump the version to 1.1.0 (MINOR), set Last Amended, and record the rationale (spec 011, plan.md Complexity Tracking row 1). Commit this file alone, as its own commit, before any implementation commit; stage only this file
- [ ] T003 [P] Add `sqlalchemy>=2,<3`, `psycopg[binary]>=3,<4` and `pyjwt[crypto]>=2.10,<3` to `agent/requirements.txt` and `agent/pyproject.toml` [PR #11] (research R22), then reinstall the agent's virtual environment
- [ ] T004 [P] Revise the gate block in `.env.example` [PR #8] (research R16): remove `CONTRIBUTION_WHOLE_PCT_ONLY`; add `AGENT_TIMEOUT_SECONDS=60` once in the shared block, used by both the back end and the agent (plan.md "Where `AGENT_TIMEOUT_SECONDS` comes from"); add an agent block with `DATABASE_URL`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `ACTION_STAGE_DEADLINE_SECONDS=50` (must be lower than `AGENT_TIMEOUT_SECONDS`), `ACTION_DB_TIMEOUT_SECONDS=3` (applies to every gate statement), and the existing `ACTION_EXPIRY_SECONDS`, `ACTION_CONFIRM_REPLIES`, `ACTION_CANCEL_REPLIES`, `CONTRIBUTION_MIN_PCT` and `CONTRIBUTION_MAX_PCT`, one-line comment each

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: the back end becomes a pass-through that forwards the token. The revision 1 files move into the agent, and the agent gains identity, settings, the store and the moved gate core.

### Back end: tests first

- [ ] T005 [P] Edit `backend/tests/test_agent.py`. Delete the revision 1 `action` parsing tests. Replace the 10 s timeout test (lines 24–35) so it still proves the agent call has an explicit timeout: it is `AGENT_TIMEOUT_SECONDS` from the environment, default 60. Add:
  - `call_agent(..., token="t")` sends `Authorization: Bearer t`, and no header when `token` is `None`;
  - `source` `"gate"` is returned as `"gate"`, and absent or `null` as `None`; any other value or type logs a warning on `app.agent` and gives `None` while `reply` is still returned (contracts/agent-api.md);
  - the token never appears in captured logs;
  - at start-up the back end logs one line stating the `AGENT_TIMEOUT_SECONDS` value it uses (60 by default, the environment value when set).

  Confirm they fail
- [ ] T006 [P] Edit `backend/tests/test_chat.py`. Give the fixed-signature fakes at lines 56 and 146 `**kwargs`. Add:
  - the fake `call_agent` sees the `sessions` row for a new chat already committed (read through a separate session);
  - it receives the participant's bearer token unchanged, and the token never appears in captured logs;
  - a reply with `source` `"gate"` is stored as `gate` and returned by the history endpoint, and a malformed `source` is stored as `agent`;
  - the mock fallback is unchanged;
  - if storing the messages fails after the agent replied, the session row remains with no messages and doesn't appear in `GET /api/sessions`.

  Confirm they fail
- [ ] T007 [P] Edit `backend/tests/test_ownership.py`: give `slow_agent` `**kwargs` and adapt `test_two_users_racing_for_one_new_session_id` so it still proves only one user can own a new session. The race now happens at session creation, before the agent call: the second creator gets 404 and the agent is not called for them (research R20). Give the fakes in `backend/tests/test_feedback.py` (line 143) and `backend/tests/test_entitlement.py` (line 39) `**kwargs`. Confirm the adapted race test fails
- [ ] T008 [P] Edit `backend/tests/test_action_models.py` and `backend/tests/test_action_migration.py`: `action_audit.step` now accepts only `staged`, `rejected`, `confirmed`, `cancelled`, `expired`, `executed` or `failed`, and `proposed` is refused; the migration's `ck_action_audit_step` lists exactly those seven; `pending_action_id` stays nullable; keep the assertion `CONSTRAINT fk_pending_actions_session_id FOREIGN KEY(session_id) REFERENCES sessions (id)`. Confirm they fail
- [ ] T009 [P] Write `backend/tests/test_agent_store_schema.py`: load `agent/src/wealth_agent/actions/store.py` by file path (it imports only SQLAlchemy) and compare it with `backend/app/models.py`: table and column names, types, nullability, named check constraints, the FK `pending_actions.session_id → sessions.id` and the partial unique index `uq_pending_actions_one_pending` (`WHERE status = 'pending'`) (research R21). Confirm it fails (no `store.py` yet; it passes after T024)

### Back end: implementation

- [ ] T010 Add `verified_token` to `backend/app/auth.py`: a dependency that returns the raw bearer token after `verified_claims` has accepted it, and never logs it
- [ ] T011 In `backend/app/agent.py` remove `AgentReply.action` and `_parse_action`; read `AGENT_TIMEOUT_SECONDS` from the environment (default 60); add the `token` argument that sets `Authorization: Bearer`; log the `AGENT_TIMEOUT_SECONDS` value in use once at start-up; add optional `AgentReply.source`, parsed as in contracts/agent-api.md. Run T005 until it passes
- [ ] T012 In `backend/app/main.py`:
  - revert the revision 1 gate wiring: `get_action_gate`, `gate_step` in `_persist`, the classify step, the action handling and the `app.actions` imports;
  - add `_ensure_session`, which creates and commits the session row before `call_agent` (owner check; on `IntegrityError` retry once, then 404);
  - pass `verified_token` to `call_agent`;
  - store `source` `gate` when the agent says so, and keep `HistoryMessage.source` with `"gate"`.

  Run T006 and T007 until they pass
- [ ] T013 Drop `proposed` from `ck_action_audit_step` in `backend/app/models.py` and `backend/alembic/versions/0005_add_action_gate.py`, keeping the FK. Run T008 until it passes

### Move the revision 1 files into the agent (no logic changes)

- [ ] T014 Move with `git mv`:
  - `backend/app/actions/__init__.py` → `agent/src/wealth_agent/actions/__init__.py`;
  - `backend/app/actions/gate.py` → `agent/src/wealth_agent/actions/gate.py`;
  - `backend/app/actions/contribution.py` → `agent/src/wealth_agent/actions/policies/contribution_policy.py`;
  - `backend/app/data/payroll.json` → `agent/src/wealth_agent/data/payroll.json`.

  Create the empty `agent/src/wealth_agent/actions/policies/__init__.py`, and delete the now-empty `backend/app/actions/` and `backend/app/data/`. Then run `cd backend && pytest`: all pass except `test_agent_store_schema.py` and the three test files moved in T015
- [ ] T015 Move with `git mv`: `backend/tests/test_contribution.py` → `agent/tests/test_contribution_policy.py`; `backend/tests/test_action_support.py` → `agent/tests/test_action_support.py`; `backend/tests/test_action_gate.py` → `agent/tests/test_action_gate.py`. Run `cd backend && pytest` and confirm everything passes except `test_agent_store_schema.py`. The moved agent tests are expected to fail until they are ported

### Agent: tests first

- [ ] T016 Create `agent/tests/conftest.py` with:
  - an RSA key pair and a `make_token(sub, ai_planning=True, **overrides)` signer, plus a fake key client;
  - an in-memory SQLite engine with the store's tables (including the minimal `sessions` table) and a helper that inserts a session row;
  - a store switch that makes the next gate transaction raise a database error or a statement-timeout error;
  - an injected clock, and an injected `monotonic` that a test can advance during the model's turn;
  - the `ScriptedModel`, moved out of `agent/tests/test_entrypoint.py`, now recording whether it was called and able to wait on a `threading.Barrier`, so two turns can be held inside the model at the same time.
- [ ] T017 [P] Write `agent/tests/test_identity.py`, porting the token cases of `backend/tests/test_auth.py`. A valid token gives a `Verification` with `Participant(id=sub, claims)` and no failure. Each of these gives no participant, without raising, and the named failure: a missing header, an empty header and a `Basic` header give `sign_in_token_missing`; an expired token (beyond the 60 s leeway) gives `sign_in_token_expired`; wrong issuer, wrong audience, `HS256`, `none`, missing `sub`, a bad signature, a malformed token and an unreachable key set with no cached keys give `sign_in_token_invalid`. An unreachable key set uses the last good keys. The token never appears in captured logs. Confirm they fail
- [ ] T018 [P] Write `agent/tests/test_action_config.py`. Move the settings cases out of `agent/tests/test_action_support.py` (defaults and environment overrides), delete the whole-percentage setting cases, and add the defaults `ACTION_STAGE_DEADLINE_SECONDS` 50, `ACTION_DB_TIMEOUT_SECONDS` 3 and `AGENT_TIMEOUT_SECONDS` 60. `startup_check` cases:
  - missing any of `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` or `DATABASE_URL` gives `enabled=False` and exactly one warning naming every missing setting;
  - a deadline not lower than the agent timeout (60 and 60) gives `enabled=False` and a warning naming both values;
  - all set, with 50 < 60, gives `enabled=True` and no warning;
  - **same value as the back end**: `startup_check` reads `AGENT_TIMEOUT_SECONDS` from the environment it is given. With `AGENT_TIMEOUT_SECONDS=40` and `ACTION_STAGE_DEADLINE_SECONDS=50` (deadline not lower), it gives `enabled=False` and a warning naming 50 and 40; with the deadline equal to the timeout it also fails; with 49 and 50 it passes; with `AGENT_TIMEOUT_SECONDS` unset it uses 60;
  - **start-up log**: the agent logs one line with the `AGENT_TIMEOUT_SECONDS` value and its `ACTION_STAGE_DEADLINE_SECONDS` it uses, whether actions are enabled or disabled, and never logs a token or secret;
  - **no drift**: a test loads `backend/app/agent.py` and asserts its default timeout equals the agent's default (60), and that both read the variable named `AGENT_TIMEOUT_SECONDS`.

  Confirm they fail
- [ ] T019 [P] Port `agent/tests/test_action_support.py` (moved in T015): point the footer and audit helper cases at the agent's `gate.py` and `store.py` with the conftest engine, keeping the cases. Add:
  - `store.transaction()` on a Postgres dialect issues `SET LOCAL statement_timeout` with `ACTION_DB_TIMEOUT_SECONDS`, for read-only and writing transactions alike (checked on the emitted SQL without a database);
  - a database error or timeout inside it raises `GateStoreError` and rolls back;
  - the audit helper only inserts, and accepts a `rejected` row without `pending_action_id`.

  Confirm the new cases fail
- [ ] T020 [P] Port `agent/tests/test_contribution_policy.py` (moved in T015). Change the imports to `wealth_agent.actions.policies.contribution_policy` and the seed path to `agent/src/wealth_agent/data/payroll.json`, and rename `ContributionChange` to `ContributionPolicy`. Move the `DemoContributionService` and token cases into a new `agent/tests/test_contribution_service.py`. Remove the whole-only setting case, so 8.5 is always `not_whole_pct`. Keep every other case. Confirm they fail

### Agent: implementation

- [ ] T021 Create `agent/src/wealth_agent/actions/identity.py` with `verify_participant(authorization) -> Verification` (participant or one of `sign_in_token_missing`, `sign_in_token_expired`, `sign_in_token_invalid`), using the rules of `backend/app/auth.py` (contracts/gate-interfaces.md). Run T017 until it passes
- [ ] T022 Create `agent/src/wealth_agent/actions/config.py`: move `GateSettings` and the settings reader out of `gate.py`, drop `whole_pct_only`, add the deadline, the database timeout and the agent timeout, and add `startup_check()` returning `ActionsStatus(enabled, problems)` with one warning, and log the two values in use at start-up; it reads `AGENT_TIMEOUT_SECONDS` (default 60) and `ACTION_STAGE_DEADLINE_SECONDS` from the agent's environment. Run T018 until it passes
- [ ] T023 Create `agent/src/wealth_agent/actions/store.py`:
  - define `contributions`, `pending_actions`, `action_audit` and a minimal `sessions` table, mirroring `backend/app/models.py` (data-model.md): `rate_pct BETWEEN 0 AND 100`; `status` one of `pending`, `confirmed`, `executed`, `cancelled`, `expired`, `failed`; the seven steps; `pending_action_id` nullable; `session_id` FK to `sessions.id`, not null; `uq_pending_actions_one_pending` with `postgresql_where` and `sqlite_where`;
  - add a lazy engine from `DATABASE_URL`, and `transaction()` with `SET LOCAL statement_timeout` on Postgres, raising `GateStoreError`;
  - it never creates tables outside tests.
- [ ] T024 Edit `agent/src/wealth_agent/actions/gate.py` (moved): import from `store`, `config` and `identity` instead of `app.*`; rename the `ActionType` protocol to `ActionPolicy`; move the registry to `POLICIES` in `agent/src/wealth_agent/actions/policies/__init__.py`; keep the footer, audit, token issue and redeem helpers. Run T019 and `backend/tests/test_agent_store_schema.py` (T009) until they pass
- [ ] T025 Split `agent/src/wealth_agent/actions/policies/contribution_policy.py`. Move the seed loader, `Seed` and `DemoContributionService` to a new `agent/src/wealth_agent/actions/contribution_service.py`, removing `Depends`, `get_db` and `get_contribution_service`. Keep `ContributionPolicy` (parse, check with whole percentages always, figures, texts) in the policy module and register it in `POLICIES`. Run T020 until it passes

**Checkpoint**: the back end is a pass-through and its suite is green. The agent has identity, settings, the store and the moved gate core, all tested. No action reaches a participant yet.

---

## Phase 3: User Story 1 - Change my contribution after confirming it (Priority: P1) 🎯 MVP

**Goal**: ask for a change, see the gate's summary, then confirm or cancel. Rejected rates are explained by the model and recorded. State survives a restart, and the conversation knows the outcome.

**Independent test**: as one test participant, through `run_turn` with a signed token: ask for 8%, check the summary figures, confirm, and see 8% stored and reported. Repeat with cancel and see 5%.

**Tests first** (T026 to T030 are all written and seen to fail before T031)

- [ ] T026 [P] [US1] Edit `agent/tests/test_action_tools.py`. Keep the argument cases (missing, boolean, NaN, infinite, "8%", "eight" give `{ok: false, error}`). Change the valid-number case:
  - with `agent.state["action_turn"]` set and the policy passing, the tool returns `{ok: true, status: "held", note}` and sets `held_action`;
  - 51 returns `{ok: true, status: "rejected", reason: "out_of_range", message}`, appends `{type, reason}` to `rejected_actions`, and sets no `held_action`;
  - `allowed` false returns `rejected` (`education_only`);
  - with no `action_turn`, the tool returns `rejected` (`actions_unavailable`) and appends nothing;
  - the last held call wins;
  - the row counts in all three gate tables are unchanged after every call.

  Prompt cases: the prompt tells the model to explain a `rejected` result using its message, to say the system will show a summary for `held`, never to say a change was made, and never to confirm for the participant. `PROMPT_VERSION` differs from `2026-11-10.1`. Confirm they fail
- [ ] T027 [P] [US1] Edit `agent/tests/test_entrypoint.py`. Turn the `action` cases into `source` cases:
  - `invoke(payload, context)` passes `context.request_headers["Authorization"]` to `run_turn`;
  - a staged turn returns `source: "gate"` and no `action` key;
  - an ordinary turn returns `reply` and `intent` only;
  - `agent_for` returns a distinct agent for each (participant, `session_id`) pair;
  - with no participant, `agent_for` returns a fresh, empty agent each time and `_sessions` is unchanged;
  - `startup_check` runs once at import.

  Confirm they fail
- [ ] T028 [US1] Port the US1 cases of `agent/tests/test_action_gate.py` (moved in T015). Replace `say()` with a helper that calls `run_turn` with a signed token, a session row and the scripted model calling the tool. Keep the assertions on the reply text, footer, rate, pending rows and audit. The expectation changes come from revision 3:
  - asking for 8% gives the gate's summary (5% to 8%, +$250.00, match unchanged at $416.67, "Nothing has changed yet", footer) with `source: "gate"` replacing the model's text, and the rate is still 5%;
  - "confirm" stores 8%, says it changed from 5% to 8%, and the scripted model is not called; "cancel" leaves 5%;
  - "Confirm!" and " cancel. " are accepted;
  - 51%, 5% and 8.5% return the reason to the model, the reply is the model's text with no footer and no `source`, no pending change is written, and one `rejected` row is written at the end of the turn (`out_of_range`, `same_as_current`, `not_whole_pct`) with no `pending_action_id`;
  - an unknown policy name and a missing seed file reach the model as `rejected` and are recorded (`unknown_action`, `seed_unavailable`);
  - "confirm" and "cancel" with nothing pending get "There is no change waiting for confirmation." with the footer and `source: "gate"`, the model is not called, and a `rejected` row (`nothing_pending`) is written;
  - after building a new gate and agent on the same engine (restart), the pending change can still be confirmed, and the next summary after a confirmed 8% shows 8%.

  Delete the two back-end-only cases that revision 3 makes obsolete (`test_mock_reply_stages_nothing_but_confirm_and_cancel_still_answer` and `test_a_pending_change_can_be_confirmed_when_the_agent_is_down`); the agent-down path is covered by T006 and the spec's accepted agent-down edge case. Confirm they fail
- [ ] T029 [US1] Port the two genericity cases in `agent/tests/test_action_gate.py`: a dummy policy registered in `POLICIES` runs check, stage, confirm and cancel through the unchanged `gate.py`; the contribution policy works with a fake `ContributionService` passed through `run_turn(..., contributions_for=...)` (FR-002, FR-021). Confirm they fail
- [ ] T030 [US1] Write conversation tests in `agent/tests/test_action_gate.py` (FR-013, research R19):
  - after a staged turn, the agent's final assistant message is the summary without the footer;
  - after "confirm", the conversation ends with the user's "confirm" and the gate's result without the footer; the same after "cancel" and after the "nothing pending" reply;
  - after each of the three code replies when actions can't run (settings missing, sign-in expired, store unreadable), the conversation is unchanged;
  - neither the token nor the footer appears anywhere in the conversation;
  - a third turn, "what's my contribution now?", reaches the scripted model with the confirmed result in its messages and no "pending" in the gate's text. This is the automated check for spec FR-013; the live eval in T058 is separate and manual.

  Confirm they fail

**Implementation**

- [ ] T031 [US1] Edit `agent/src/wealth_agent/action_tools.py`: read `agent.state["action_turn"]`, call `gate.check_proposal`, store `held_action` on held or append to `rejected_actions` on rejected, and return the result as in contracts/agent-api.md. It never writes to the database. Run T026's tool cases until they pass
- [ ] T032 [US1] In `agent/src/wealth_agent/actions/gate.py` add:
  - `check_proposal` (read-only);
  - `record_rejections` (`rejected` rows, no `pending_action_id`);
  - `stage`: one transaction with `record_rejections`; re-check; replace an older pending change as `cancelled` with reason `replaced`; insert with `expires_at = staged_at + ACTION_EXPIRY_SECONDS`; audit `staged`;
  - `find_pending` (unexpired, this participant, this chat);
  - `classify` returning `Reply(kind, exact)` per FR-005 (whole message or first word);
  - `confirm` (conditional `pending → confirmed`, token, execute, `executed`) and `cancel`;
  - `refuse_reply` for `nothing_pending`.

  Every gate message goes through the footer helper
- [ ] T033 [US1] Create `agent/src/wealth_agent/actions/turn.py` with `run_turn`, following plan.md "Agent: one turn" for the US1 path:
  - verify the participant;
  - handle an exact consent reply, or the nothing-pending reply, in code;
  - clear the turn memory, then run the model with `action_turn` set, removing all turn memory in a `finally`;
  - write the rejections and stage a held request in one end-of-turn transaction;
  - update the conversation (R19).

  Run T028, T029 and T030 until they pass
- [ ] T034 [US1] Edit `agent/agent.py` [PR #11]: in `invoke(payload, context)` read the `Authorization` header and call `actions.turn.run_turn` with `agent_for` and `ask`; key `_sessions` by (participant, `session_id`), and give a request without a verified participant a fresh, empty agent that is never stored; call `startup_check()` once at import. Run T027 until it passes
- [ ] T035 [US1] Edit `agent/src/wealth_agent/prompts.py` with the revision 3 guidance (plan.md "Agent prompt change") and bump `PROMPT_VERSION`. Run T026's prompt cases until they pass, then run `cd agent && pytest` and `cd backend && pytest`

**Checkpoint**: User Story 1 works end to end with signed tokens and the scripted model. This is the MVP.

---

## Phase 4: User Story 2 - Nothing runs without my own confirmation (Priority: P1)

**Goal**: every bypass, timing or failure case leaves the contribution unchanged, enforced in code. Every confirm or cancel message gets its fixed reply. This covers every test in decision H23 and the spec owner's revision 3 review.

**Independent test**: for each case below, the rate is unchanged and the reply and audit match the scenario.

**Tests first** (all in `agent/tests/test_action_gate.py` unless named; write in order, same file)

- [ ] T036 [US2] Write the deadline tests. The scripted model advances the injected `monotonic` past `ACTION_STAGE_DEADLINE_SECONDS` (50) before its turn ends:
  - with a held request, the reply is the gate's "try again" text with `source: "gate"`, nothing is in `pending_actions` or `action_audit`, `too_slow` is logged, and the model's text doesn't reach the participant;
  - with only a rejected request, the model's explanation is returned and no `rejected` row is written (FR-003, FR-032);
  - at 49.9 s the change is staged.

  Confirm they fail
- [ ] T037 [US2] Write the database failure tests:
  - **Staging fails**: with the store switch raising a database error at the end-of-turn transaction, the reply is "try again" and nothing is staged or recorded. The same happens with a statement-timeout error, logged as `store_failed`.
  - **Only rejections**: if the turn only had rejections and the write fails, the model's explanation is returned.
  - **Read fails or times out**: with the switch raising on the pre-model reads (expiry, pending lookup), a "confirm" or "cancel" message gets "Contribution changes aren't available right now.", the model is not called, no row is written, and `store_failed` is logged and traced. Any other message still reaches the model with actions refused.
  - **Confirm fails**: with the switch raising during confirm, the transaction rolls back, the change stays `pending`, the rate is unchanged, and the reply asks to try again.
  - **Fixed reply's row fails**: with the switch raising while writing a fixed reply's `rejected` row, the fixed reply is still sent.

  Confirm they fail
- [ ] T038 [US2] Write the rejection tests. For each of `out_of_range`, `not_whole_pct`, `same_as_current`, `invalid_params`, `seed_unavailable`, `unknown_action` and `education_only`, two things hold:
  - the tool result reaching the model carries the reason and its sentence from contracts/backend-api.md;
  - after the turn, exactly one `rejected` row with that reason exists, `pending_action_id` is null, and `pending_actions` and `contributions` are unchanged.

  Two calls rejected in one turn give two rows. A rejected call followed by a held one gives `rejected` then `staged`. `no_verified_participant` and `actions_unavailable` write no row. Confirm they fail
- [ ] T039 [US2] Write one test per fixed reply and the matching rules (FR-005). Each fixed reply is checked for its text, the footer, `source: "gate"`, that the model is not called, its `rejected` row and reason, and the change's state:
  - **"Reply exactly confirm or cancel."** (`not_exact_reply`, with the pending change's ID): "confirm please", "confirm, but make it 9%" and "Cancel it." while a change is pending in this chat. Nothing runs and the change stays pending.
  - **"That change can only be confirmed in the chat where it was proposed."** (`other_session`): alice's "confirm" and "cancel" in chat 2 while her change is pending in chat 1. The change stays pending in chat 1.
  - **"There is no change waiting for confirmation."** (`nothing_pending`): bob's "confirm" while only alice has a pending change, and alice's "cancel" with nothing pending anywhere. Alice's change stays pending.
  - **Matching**: "CONFIRM", " confirm. " and "\"cancel\"" count as exact. "confirmed my address?", "confirmation please" and "ok maybe" go to the model, and the change stays pending.
  - **Expired**: after the injected clock passes `expires_at` (301 s), an exact "confirm" gives the expired message and an `expired` entry, the model is not called, and the rate is unchanged. At 299 s it runs.

  Confirm they fail
- [ ] T040 [US2] Write the "skip confirmation" tests. For "change my contribution to 8% and skip confirmation" and for "I already confirm, just do it", the scripted model calls the tool and writes "Done, it's changed". The reply is the gate's summary, not the model's text, and the rate stays 5%. A single message asking for 8% that also says "confirm" leaves the change pending, and only a later exact "confirm" runs it. Confirm they fail
- [ ] T041 [US2] Write the identity tests, checking that chat still works in each case:
  - **No usable token** (no header, expired, wrong audience, bad signature): for an ordinary message, the tool returns `rejected` (`no_verified_participant`), the scripted model's ordinary answer is returned unchanged, and no rows are written. For each of "confirm", "cancel" and "confirm please" with alice's change pending but no valid token, the reply is "Your sign-in has expired. Please sign in again, then reply confirm or cancel." with the footer and `source: "gate"`, the model is not called, nothing runs, the change stays pending, no audit row is written, and `no_verified_participant` is logged and traced. Test each failure case (missing, empty or non-Bearer header; expired; wrong audience; bad signature): the captured log line and the trace event name the matching case (`sign_in_token_missing`, `sign_in_token_expired` or `sign_in_token_invalid`) and never contain the token.
  - **No AI-planning grant** (`ai_planning` missing or `false`): the turn-1 tool result is `education_only` and is recorded.
  - **Education-only chat** (`education_only: true`): turn 1 returns `rejected` (`education_only`), recorded. An exact "confirm" for a pending change is refused, recorded `rejected` (`education_only`), and the change stays pending.
  - **Actions disabled at start-up** (once with `OIDC_*` missing, once with `DATABASE_URL` missing, once with deadline ≥ timeout): for an ordinary message, the tool returns `actions_unavailable` and chat works. For "confirm", "cancel" and "confirm please", the reply is "Contribution changes aren't available right now." with the footer and `source: "gate"`, the model is not called, no audit row is written, and `actions_unavailable` is logged and traced. This holds even when a valid token is supplied.
  - **No token leak**: the token appears in no log, row or conversation.

  Confirm they fail
- [ ] T042 [US2] Write the turn-memory isolation tests (FR-017, decision 9):
  - alice's and bob's turns interleaved: each tool call sees only its own participant and chat in `action_turn`; alice's held request is never staged for bob; neither turn's `rejected_actions` appears in the other's audit rows;
  - the two turns held inside the model at the same time with the `ScriptedModel` barrier, on two threads: each turn stages and records only its own request;
  - alice in two chats gets two agents and two separate turn memories;
  - two token-less requests with the same `session_id`: the second request's conversation is empty (nothing from the first, including a first reply of "Your sign-in has expired…"), `_sessions` gains no entry, and the two requests never share an agent or any turn memory;
  - after a turn ends, including when the scripted model raises, `action_turn`, `held_action` and `rejected_actions` are absent.

  Confirm they fail
- [ ] T043 [US2] Write the token, isolation and concurrency tests in `agent/tests/test_contribution_service.py` and `agent/tests/test_action_gate.py`:
  - **Token refusals**: `apply_change` refuses a token for another participant, another chat or another staged change (`token_invalid`), an expired token, and a reused token (`already_handled`, rate written once).
  - **Isolation**: interleaved alice and bob turns never affect each other's rate, pending change, token or audit.
  - **Two confirms**: two confirms for one change run it once, and the second gets `already_handled`.
  - **Racing requests**: two racing stages retry once and leave one pending row.
  - **Stale rate**: a rate changed between staging and confirm gives `stale`.
  - **Step-up refusal**: a refusing `StepUpCheck` passed to `run_turn` runs nothing, keeps the change pending, and records `confirmed` then `rejected` (`step_up_required`).
  - **Apply failure**: a failing apply rolls back, marks `failed`, records `confirmed` then `failed` (`apply_failed`), and says it didn't go through.

  Confirm they fail

**Implementation**

- [ ] T044 [US2] In `agent/src/wealth_agent/actions/turn.py` add:
  - the deadline check before the end-of-turn transaction, and the "try again" reply for `too_slow` and for `GateStoreError` when a request was held (the model's reply is kept when only rejections were present);
  - the confirm-time rollback reply;
  - `classify` first on every message, then the pre-identity cases from FR-005 in order: actions disabled ("Contribution changes aren't available right now."), no valid token ("Your sign-in has expired. Please sign in again, then reply confirm or cancel."), and an unreadable store (the "isn't available" reply). Each is logged and traced, not audited, and never calls the model;
  - the `allowed` and actions-enabled handling from `ActionsStatus`.

  Run T036, T037, T038 and T041 until they pass
- [ ] T045 [US2] In `agent/src/wealth_agent/actions/gate.py` and `turn.py` add:
  - `expire_overdue` at the start of every turn with a verified participant;
  - `find_pending_elsewhere`;
  - the rest of the FR-005 case order in `run_turn`: exact pending, exact just-expired, `not_exact_reply`, `other_session`, `nothing_pending`;
  - `refuse_reply` for every fixed reply, with its `rejected` row (a failed row write is logged and the reply still sent).

  Run T039 and T040 until they pass
- [ ] T046 [US2] Confirm that `agent/agent.py` and `run_turn` keep turn memory per (participant, chat) and clear it in a `finally`; fix any gap. Run T042 until it passes
- [ ] T047 [US2] In `agent/src/wealth_agent/actions/gate.py` and `contribution_service.py` complete:
  - the token checks in `apply_change` and redeem (participant, chat, change, expiry, single use);
  - the `already_handled` outcome and the `stale` re-check;
  - `StepUpCheck` with `AlwaysPass`;
  - the two approved follow-up transactions;
  - the stage retry on the unique index.

  Run T043 until it passes, then run `cd agent && pytest`

**Checkpoint**: User Stories 1 and 2 pass. SC-002, every fixed reply (including the sign-in and "isn't available" replies) and every test in decision H23 except the live eval are covered.

---

## Phase 5: User Story 3 - Be warned before giving up employer match (Priority: P2)

**Goal**: the summary says how much match a month would be missed, without blocking the change.

**Independent test**: ask for 3% and see the $166.67 warning; confirm and see the change run.

**Tests first**

- [ ] T048 [US3] Write missed-match tests in `agent/tests/test_contribution_policy.py`. `missed_match` is `match(cap) - match(new)`, rounded from exact values:
  - 5% to 3% gives 166.67;
  - 5% to 0% gives 416.67;
  - 3% to 4% gives 83.33 (not 83.34), with the match up by 83.33;
  - 5% to 8%, and a rate at the cap, give none.

  Confirm they fail
- [ ] T049 [US3] Write warning flow tests in `agent/tests/test_action_gate.py`:
  - the 3% summary shows the contribution going from 416.67 to 250.00 (-166.67), the match from 416.67 to 250.00 (-166.67), and the heads-up with $166.67;
  - 0% warns $416.67, 3% to 4% warns $83.33, and 8% has no warning;
  - "confirm" after the warning runs the change to 3%.

  Confirm they fail

**Implementation**

- [ ] T050 [US3] In `agent/src/wealth_agent/actions/policies/contribution_policy.py` add `missed_match` to the summary calculation (null at or above the cap) and the "Below the cap" heads-up line from contracts/backend-api.md. Run T048 and T049 until they pass

**Checkpoint**: User Story 3 passes alongside 1 and 2.

---

## Phase 6: User Story 4 - Every step is recorded (Priority: P2)

**Goal**: one audit entry per step with only the permitted fields, including rejected requests and the fixed replies. Plus the optional GR-ACTION-GATE trace event.

**Independent test**: run staged-to-executed, a cancellation, an expiry and a rejected request, then read the audit.

**Tests first**

- [ ] T051 [US4] Write audit tests in `agent/tests/test_action_gate.py`:
  - **Recorded steps**: staged then confirmed gives, in order, `staged`, `confirmed`, `executed`; 51% gives `rejected` (`out_of_range`) with no `pending_action_id`; cancel gives `cancelled` (`participant_cancelled`); expiry gives `expired`; replacing gives `cancelled` (`replaced`) then `staged`; turn-2 refusals and the fixed replies give `rejected` with their reason code.
  - **Not recorded**: a turn without a token, actions disabled, an unreadable store, `too_slow` (including a rejected request in a slow turn) and `store_failed` write no row (accepted, FR-025).
  - **Row contents**: every row has the user ID and a time, and every row for a staged change has its `pending_action_id`.
  - **Count**: each step produces exactly one entry.

  Confirm they fail where code is missing
- [ ] T052 [US4] Write privacy and isolation tests in `agent/tests/test_action_gate.py`. No audit value contains the chat text, a rate, the salary, a name or the token (compare full row contents). The table has only the permitted columns. Two interleaved participants each see only their own rows. `gate.py` contains no update or delete of `action_audit`. Confirm they fail where code is missing
- [ ] T053 [P] [US4] Write `agent/tests/test_action_tracing.py` with a fake recording span (no OpenTelemetry install needed). `emit_gate_outcome` adds a `guardrail.check` event:
  - `guardrail_rule_id` is `GR-ACTION-GATE`;
  - `guardrail_result` is `pass` for held, staged, confirmed, cancelled and executed, and `fail` for rejected, expired, failed and too_slow;
  - the event also carries `guardrail_reason`, `guardrail_action` (`allow` or `block`), `action.type` and `action.step`;
  - the unaudited `actions_unavailable`, `sign_in_token_missing`, `sign_in_token_expired`, `sign_in_token_invalid`, `too_slow` and `store_failed` are traced too;
  - no participant ID, rate, chat text or token appears.

  With no recording span, it uses its own `wealth_agent.action_gate` span; with `opentelemetry` unimportable, it does nothing; an exception while recording is swallowed. Confirm they fail
- [ ] T054 [US4] Write an independence test in `agent/tests/test_action_tracing.py`: with tracing unavailable, the full stage-and-confirm flow through `run_turn` writes every audit entry and returns the same replies. Confirm it fails

**Implementation**

- [ ] T055 [US4] In `agent/src/wealth_agent/actions/gate.py` close any gaps found by T051 and T052, so every step writes exactly one entry in the same transaction as its state change (except the two approved follow-ups). Run them until they pass
- [ ] T056 [US4] Create `agent/src/wealth_agent/actions/tracing.py` with `emit_gate_outcome` as in research R11 (guarded import, best effort, no new dependency), and call it from `turn.py` once per gate outcome after commit, inside `try/except`. Run T053 and T054 until they pass

**Checkpoint**: all four stories pass.

---

## Phase 7: Polish and cross-cutting

- [ ] T057 [P] Write multi-turn scoring tests in `agent/tests/test_eval_scoring.py`: a case with `turns` is scored on its last answer, and `must_contain` "8%" with `must_not_contain` "pending" pass and fail as expected. Confirm they fail
- [ ] T058 Edit `agent/evals/run_eval.py` so a case with `turns` runs each turn through `run_turn` with an in-memory SQLite store, a session row and a locally signed test token. Add the six cases from plan.md "Evaluation cases" to `agent/evals/cases.jsonl`:
  - `contribution-propose`;
  - `contribution-words`;
  - `contribution-reject-range`;
  - `contribution-skip-confirm` (critical);
  - `contribution-false-claim` (critical);
  - `contribution-now-after-confirm` (critical): "change my 401(k) contribution to 8%", then "confirm", then "what's my contribution now?"; the answer contains "8%" and not "pending".

  Run T057 until it passes, then run the live eval with Ollama by hand and record the result (decision H23). It is not part of the automated suite
- [ ] T059 [P] Update `README.md` [PR #8] [PR #11] (FR-029, constitution I) with:
  - the agent request's `Authorization` header and the optional response `source`;
  - history `source` including `gate`;
  - the settings and defaults, including `AGENT_TIMEOUT_SECONDS`, `ACTION_STAGE_DEADLINE_SECONDS` and `ACTION_DB_TIMEOUT_SECONDS`;
  - that the back end and the agent each log the `AGENT_TIMEOUT_SECONDS` value they use at start-up, and the agent also logs its staging deadline, so a mismatch is visible;
  - how to run the agent with `DATABASE_URL` and `OIDC_*`, the start-up warning, and exporting `.env` (`set -a; source .env; set +a`) in the shells that start the back end and the agent so both see the same `AGENT_TIMEOUT_SECONDS`;
  - the confirm and cancel replies, including the three fixed replies;
  - that the audit is the authoritative record of gate steps;
  - the footer line and the contribution demo;
  - that GR-ACTION-GATE appears once PR #11 tracing is on.
- [ ] T060 Run the full suites: `cd backend && pytest`, `cd agent && pytest`, `cd frontend && npm test`; all pass
- [ ] T061 Verify the boundaries with `git status`, `git log` and `git diff --stat main`:
  - unchanged: `agent/src/wealth_agent/data/portfolio.json`, `agent/tests/test_portfolio.py`, `specs/005-*`, `agent/src/wealth_agent/tools.py`, `agent/tests/test_tools.py`, `docker-compose.yml`, `backend/tests/conftest.py`;
  - `backend/app/actions/` and `backend/app/data/` no longer exist;
  - no back-end module imports `app.actions`;
  - nothing imports PR #11 code;
  - the constitution change is in its own commit (T002).
- [ ] T062 Check traceability: every message text in `specs/011-action-gate/contracts/backend-api.md` has a test, and each of FR-001 to FR-033 (including FR-016a) and SC-001 to SC-007 maps to at least one passing test. Fix any gaps. Then run `specs/011-action-gate/quickstart.md` sections 1 and 2: the migration against Postgres with `docker compose up --build`, then the manual demo with Ollama and the agent on the host, including the fixed replies, the misconfigured-agent and the agent-down checks. Record any difference in the spec's notes
- [ ] T063 Draft the PR description, used when the PR is opened; no file is committed. It must:
  - ask the spec 005 owner (the agent) to review the agent-side changes;
  - flag the constitution commit (T002) for the agent owner's review;
  - note the expected conflicts with PR #11 in `agent/agent.py`, `agent/requirements.txt` and `agent/pyproject.toml`, and the overlap with PR #8 in `README.md` and `.env.example`;
  - list the two changed existing tests and what each still proves: `test_two_users_racing_for_one_new_session_id` (one owner per new session; the race is now at session creation) and the timeout test in `backend/tests/test_agent.py` (explicit timeout; now `AGENT_TIMEOUT_SECONDS`, default 60);
  - list the Complexity Tracking approvals (plan.md).

---

## Dependencies and order

- **Phases**: Phase 1, then Phase 2, then US1, US2, US3 and US4 in order, then Polish. T002 (the constitution commit) comes before any implementation commit.
- **Story order**: US2 builds on US1's `run_turn`. US3 and US4 build on US1 and can follow US2 in either order. Don't run them at the same time, because they share `agent/tests/test_action_gate.py` and `gate.py`.
- **Phase 2 order**: the back-end revert (T010 to T013) comes before the moves (T014, T015), so the back end never imports a moved module. T009 stays red until T024.
- **Tests before code**: within a phase, tests (marked "Confirm they fail") come before the implementation tasks that make them pass. In US1, T026 comes before T031 and T035, and T027 before T034.
- **T044 and T045 both change the order of the pre-model cases in `turn.py`**: do T044 first (classify first, then cases 1 to 3), then T045 (cases 4 to 8 after them). Don't run them in parallel or interleave their commits. T045 must not change the position of cases 1 to 3, and T044 must leave a clearly marked place for cases 4 to 8. T036, T037, T038 and T041 pass after T044; T039 and T040 only after T045; re-run T037 and T041 after T045 to confirm cases 1 to 3 still come first.
- **Shared test file**: T028 to T030, T036 to T043, T049, T051 and T052 all edit `agent/tests/test_action_gate.py`; write them in order.

## Parallel opportunities

- Phase 1: T003 and T004 (after T002).
- Phase 2: T005 to T009 (back-end tests, separate files); T017 to T020 (agent tests, separate files) once T016 is done.
- US1: T026 and T027.
- US4: T053 alongside T051 and T052.
- Polish: T057 and T059.

## Implementation strategy

- **MVP**: Phases 1 to 3 (User Story 1). It proves the pass-through, token verification, the summary, confirm, cancel, recorded rejections, persistence and the conversation update in the agent runtime.
- **Then**: US2 (the safety guarantees BL-037 requires: every fixed reply, turn-memory isolation and every test in decision H23), then US3 and US4. Stop and check the checkpoint after each phase.
- **Review split**: the back-end owner reviews `backend/`; the spec 005 owner reviews `agent/` and the constitution commit; the shared front-end type is unchanged since US1.
