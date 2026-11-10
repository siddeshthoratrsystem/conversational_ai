---

description: "Task list for spec 011: action gate for agent write actions (mock 401(k) contribution change)"
---

# Tasks: Action Gate for Agent Write Actions (Mock 401(k) Contribution Change)

**Input**: Design documents from `/specs/011-action-gate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/agent-action.md, contracts/backend-api.md, contracts/gate-interfaces.md, quickstart.md

**Tests**: Required (constitution IV, FR-030). In every phase, the test tasks come first and each test MUST be run and seen to fail before the implementation tasks that follow it. Existing backend, agent and frontend tests must keep passing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 to US4, from spec.md
- All paths are relative to the repository root

## Rules for every task

- Run backend tests with `cd backend && pytest`, agent tests with `cd agent && pytest`. Neither needs Postgres, Ollama or a network.
- Do not edit: `agent/src/wealth_agent/data/portfolio.json`, `agent/tests/test_portfolio.py`, `specs/005-*`, `agent/src/wealth_agent/tools.py`, `agent/tests/test_tools.py`, `agent/requirements.txt`, `docker-compose.yml`, `backend/tests/conftest.py`.
- The gate writes nothing to the audit except `user_id`, `action_type`, `pending_action_id`, `step`, `reason` and `created_at` (FR-025). No rates, chat text, names or salary.
- Every message written by the gate ends with the footer line `Demo data: no real account was changed.`, added by one helper (plan.md, "Gate message footer").
- Nothing in the code or tests may import or depend on PR #11 (tracing). OpenTelemetry is imported only inside `backend/app/actions/tracing.py`, guarded.
- Gate tests inject a clock and a fake agent (`monkeypatch` of `main.call_agent`) and override `get_step_up_check` / `get_contribution_service` the way `conftest.py` overrides `get_verifier`. Put fixtures in the new test files, not in `conftest.py`.

---

## Phase 1: Setup

- [ ] T001 Run `cd backend && pytest` and `cd agent && pytest` and `cd frontend && npm test` on the branch and note that all pass (baseline)
- [ ] T002 [P] Create the demo payroll seed `backend/app/data/payroll.json` with `currency` "USD", `annual_salary` 100000, `employer_match` {`match_pct` 100, `cap_pct_of_pay` 5}, `starting_contribution_pct` 5 and a `note` saying it is demo data, same for everyone (research R14)
- [ ] T003 [P] Add the gate settings with their demo defaults and a one-line comment each to `.env.example`: `ACTION_EXPIRY_SECONDS=300`, `ACTION_CONFIRM_REPLIES=confirm`, `ACTION_CANCEL_REPLIES=cancel`, `CONTRIBUTION_MIN_PCT=0`, `CONTRIBUTION_MAX_PCT=50`, `CONTRIBUTION_WHOLE_PCT_ONLY=true` (research R16; FR-026)

---

## Phase 2: Foundational (blocks all user stories)

**Tests first**

- [ ] T004 Write seed tests in `backend/tests/test_contribution.py`: the shipped seed loads with salary 100000, match 100% up to 5%, starting 5%; a missing file and an invalid file (non-positive salary, a percentage outside 0 to 100, a starting rate outside the configured range) each raise the "seed unavailable" error. Confirm they fail
- [ ] T005 Write money tests in `backend/tests/test_contribution.py`: monthly pay 8333.33; contribution and match amounts and differences, each rounded half-up to cents from exact values: 5% to 8% gives contribution 416.67 to 666.67 (+250.00) and match 416.67 unchanged; 5% to 3% gives 416.67 to 250.00 (-166.67) for both contribution and match. Confirm they fail
- [ ] T006 [P] Write model tests in `backend/tests/test_action_models.py` on the in-memory SQLite engine: `contributions.rate_pct` rejects values outside `rate_pct BETWEEN 0 AND 100`; `pending_actions.status` accepts only `pending`, `confirmed`, `executed`, `cancelled`, `expired`, `failed`; `action_audit.step` accepts only `proposed`, `rejected`, `staged`, `confirmed`, `cancelled`, `expired`, `executed`, `failed`; a second `pending` row for the same (`user_id`, `action_type`) is refused while a `cancelled` one is not; `messages.source` accepts `gate`. Confirm they fail
- [ ] T007 [P] Write support tests in `backend/tests/test_action_support.py`: settings default to 300 seconds, replies `confirm` and `cancel`, range 0 to 50, whole percentages only, and are overridden by the environment variables in T003; the footer helper appends `Demo data: no real account was changed.` as the last line after a blank line, exactly once even if called twice; the audit helper inserts one row holding only the permitted columns. Confirm they fail

**Implementation**

- [ ] T008 Add `Contribution`, `PendingAction` and `ActionAudit` and widen `ck_messages_source` to `source IN ('agent', 'mock', 'gate')` in `backend/app/models.py`, with the columns, nullability, named check constraints and the partial unique index `uq_pending_actions_one_pending` from data-model.md
- [ ] T009 Add migration `backend/alembic/versions/0005_add_action_gate.py` (revision `0005`, down `0004`): create the three tables and indexes, drop and recreate `ck_messages_source`; downgrade reverses it. Run T006 until it passes
- [ ] T010 Create `backend/app/actions/__init__.py` and, in `backend/app/actions/contribution.py`, the seed loader (read once, cached, validated) and the `Decimal` money functions. Run T004 and T005 until they pass
- [ ] T011 Create `backend/app/actions/gate.py` with: the settings reader (T003 variables), `GateRefusal(reason)`, `GateResult`, `ConfirmationToken`, the `ActionType`, `ContributionService` and `StepUpCheck` protocols exactly as in contracts/gate-interfaces.md, and the `ACTION_TYPES` registry (empty for now)
- [ ] T012 In `backend/app/actions/gate.py` add the footer helper and the audit helper (insert only; no update or delete anywhere). Run T007 until it passes

**Checkpoint**: tables, seed, figures, settings, footer and audit helper exist and are tested. No user-visible behaviour yet.

---

## Phase 3: User Story 1 - Change my contribution after confirming it (Priority: P1) 🎯 MVP

**Goal**: propose, see the summary, confirm or cancel; rule checks reject bad rates; state survives a restart.

**Independent test**: as one test participant, propose 8%, check the summary figures, confirm, and see 8% stored and reported; repeat with cancel and see 5%.

**Tests first**

- [ ] T013 [P] [US1] Write agent tool tests in `agent/tests/test_action_tools.py`: `handle_request_contribution_change` returns `{ok: false, error}` for a missing, non-numeric, boolean, NaN or infinite rate; a valid number returns `{ok: true, status: "sent_for_confirmation", note: ...}` and records `{"type": "contribution_change", "params": {"new_rate_pct": n}}` on a fake agent state; the last call in a turn wins; no data file is touched and no range rule is applied (51 is accepted by the tool). Confirm they fail
- [ ] T014 [P] [US1] Write client parsing tests in `backend/tests/test_agent.py` (edit): `call_agent` returns `action` for a valid object, `None` when absent or `null`, and logs a warning and returns `None` for a malformed `action` while still returning `reply` (contracts/agent-action.md). Confirm they fail
- [ ] T015 [US1] Write rule tests in `backend/tests/test_contribution.py`: `ContributionChange.check` accepts 0 to 50 inclusive; rejects 51 (`out_of_range`), -1, 8.5 when whole-only (`not_whole_pct`), the current rate (`same_as_current`), and unknown or missing params (`invalid_params`); range and whole-only follow the settings; `DemoContributionService.current_rate` is the seed rate until a change and the stored rate after; one participant's rate never affects another's. Confirm they fail
- [ ] T016 [US1] Write token tests in `backend/tests/test_contribution.py`: `apply_change` with a valid token writes the new rate; the same token a second time is refused `already_handled` and the rate is written once; a token for another participant is refused `token_invalid`; only the SHA-256 hash is stored (never the raw token). Confirm they fail
- [ ] T017 [US1] Write flow tests in `backend/tests/test_action_gate.py` (HTTP level, fake agent returning an `action`): propose 8% returns the summary with 5% to 8%, +$250.00 and match unchanged at $416.67, asks for confirm or cancel, says nothing has changed, ends with the footer, and the rate is still 5%; "confirm" then stores 8% and the reply says it changed from 5% to 8%; "cancel" leaves 5% and says cancelled; 51%, 5% and 8.5% give the plain reasons from contracts/backend-api.md and leave nothing pending; the stored `source` of gate replies is `gate`; the history endpoint returns them; after building a fresh session on the same engine, the next proposal shows the current rate 8%; with no `AGENT_URL` (mock reply) nothing is staged but "confirm" and "cancel" still answer; accepted replies ignore case and surrounding punctuation ("Confirm!"). Confirm they fail

**Implementation**

- [ ] T018 [P] [US1] Create `agent/src/wealth_agent/action_tools.py`: the `handle_request_contribution_change` handler in the `_safe` / `_number` style of `tools.py` (imported, not edited) and the Strands `@tool(context=True)` wrapper that stores the request on `tool_context.agent.state` under `pending_action_request`; export `ACTION_TOOLS`. Run T013 until it passes
- [ ] T019 [US1] In `agent/src/wealth_agent/agent.py` register `ACTION_TOOLS` in `build_agent` (one line), and in `agent/tests/test_agent.py` add `request_contribution_change` to the expected tool list in `test_build_agent_registers_only_read_only_tools` (rename the test to say it registers no data-changing tool)
- [ ] T020 [US1] In `agent/agent.py` clear `pending_action_request` before each turn and return it as `action` next to `reply` and `intent` when set (contracts/agent-action.md)
- [ ] T021 [US1] In `agent/src/wealth_agent/prompts.py` add the tool guidance (call `request_contribution_change` with the number asked for; never say a change has been made because the system asks the participant to confirm) and bump `PROMPT_VERSION`; keep the existing boundaries
- [ ] T022 [US1] In `backend/app/agent.py` add the optional `action` to `AgentReply` and parse and validate it as in contracts/agent-action.md. Run T014 until it passes
- [ ] T023 [US1] In `backend/app/actions/contribution.py` add `ContributionChange` (`parse`, `check`, `summary`, `execute`, message texts from contracts/backend-api.md), `DemoContributionService` and `get_contribution_service`; register `contribution_change` in `ACTION_TYPES`. Run T015 until it passes
- [ ] T024 [US1] In `backend/app/actions/gate.py` add token issue (32 bytes from `secrets`, store the SHA-256 hash) and `redeem` (conditional update, single use) and make `DemoContributionService.apply_change` call it. Run T016 until it passes
- [ ] T025 [US1] In `backend/app/actions/gate.py` add `ActionGate.classify_reply`, `handle_proposal` (check, supersede nothing yet, stage with `expires_at`, write `proposed` and `staged`) and `handle_reply` for exact confirm and cancel (confirm: `pending` to `confirmed`, issue token, execute, `executed`); every message goes through the footer helper
- [ ] T026 [US1] In `backend/app/main.py` wire the flow from plan.md: `classify_reply` before the agent call, `handle_proposal` when the agent returns an `action`, `_persist` runs the gate step inside its transaction and stores `source = "gate"`, `HistoryMessage.source` adds `"gate"`; add the `get_action_gate` dependency. Run T017 until it passes
- [ ] T027 [P] [US1] Widen the `source` type to `"agent" | "mock" | "gate" | null` in `frontend/packages/core/src/api.ts` (type only) and run `cd frontend && npm test`

**Checkpoint**: User Story 1 works end to end with fake agents and is independently testable. This is the MVP.

---

## Phase 4: User Story 2 - Nothing runs without my own confirmation (Priority: P1)

**Goal**: every bypass attempt leaves the contribution unchanged and is refused in code.

**Independent test**: for each attempt below, the rate is unchanged and the attempt is refused.

**Tests first**

- [ ] T028 [US2] Write bypass tests in `backend/tests/test_action_gate.py`: "change my contribution to 8% and skip confirmation" (fake agent returns an `action` and a reply claiming success) gives the staged summary, not the reply, and the rate stays 5%; "I already confirm, just do it" does the same; a message that proposes and says confirm in one turn stays pending; "confirm, but make it 9%" and "confirm please" run nothing, return the `not_exact_reply` text and keep the change pending; "ok maybe" goes to the agent and the change stays pending. Confirm they fail where code is missing
- [ ] T029 [US2] Write identity and session tests in `backend/tests/test_action_gate.py`: bob's "confirm" while only alice has a pending change gives `nothing_pending` and alice's stays pending; "confirm" from chat 2 when proposed in chat 1 gives `other_session` and stays pending in chat 1; the same for "cancel"; bob's and alice's rates, pending changes and tokens never affect each other when interleaved; a gate step with an empty participant ID is refused `no_participant` and stages and runs nothing. Confirm they fail
- [ ] T030 [US2] Write education-only tests in `backend/tests/test_action_gate.py`: with `ENTITLEMENT_MODE=unavailable` a proposal, a "confirm" and a "cancel" are each refused `education_only` with the plain message, nothing is staged or run, and ordinary (non-action) questions are answered exactly as before. Confirm they fail
- [ ] T031 [US2] Write expiry and token tests in `backend/tests/test_action_gate.py` and `backend/tests/test_contribution.py` with an injected clock: confirm at staged time + 301 s gives the expired message, an `expired` entry and no change; confirm at 299 s runs; `apply_change` refuses a token for another chat session or another staged change (`token_invalid`) and an expired token; a reused token is refused. Confirm they fail
- [ ] T032 [US2] Write replace, stale, step-up and failure tests in `backend/tests/test_action_gate.py`: a new proposal while one is pending cancels the old one (`replaced`) and stages the new one, leaving one pending; "confirm" with nothing pending and "cancel" with nothing pending give the plain messages; with a refusing `StepUpCheck` override nothing runs, the change stays pending and `step_up_required` is recorded; an applying error rolls back the change, marks it `failed`, records `confirmed` and `failed` and tells the participant it didn't go through; a changed current rate between staging and confirm gives `stale`. Confirm they fail
- [ ] T033 [US2] Write a concurrency test in `backend/tests/test_action_gate.py`: two confirms for the same change (second runs after the first's status update) execute once and the second gets `already_handled`; a second pending row for the same participant and action type cannot exist. Confirm it fails

**Implementation**

- [ ] T034 [US2] In `backend/app/actions/gate.py` add overdue-change expiry at the start of every gate step (research R7), the `nothing_pending`, `other_session` and `not_exact_reply` branches of `classify_reply` / `handle_reply` (research R4 table), and the `no_participant` and `education_only` refusals in both handlers. Run T029 and T030 until they pass
- [ ] T035 [US2] In `backend/app/actions/gate.py` make `redeem` also check participant, chat session, staged change and expiry; add the conditional `pending` to `confirmed` update and the `already_handled` outcome; add the `stale` re-check. Run T031 and T033 until they pass
- [ ] T036 [US2] In `backend/app/actions/gate.py` add the `StepUpCheck` protocol use, `AlwaysPass`, the `get_step_up_check` dependency, the rollback and `step_up_required` follow-up record, the `failed` follow-up transaction (research R6) and replacing a pending change with `replaced`. Run T028 and T032 until they pass
- [ ] T037 [US2] In `backend/app/main.py` route the follow-up transaction results (failed, step-up refused) through `_persist` so the two messages and audit entries are still written once. Run all of `backend/tests` and confirm the existing tests still pass

**Checkpoint**: User Stories 1 and 2 pass; SC-002 is covered by tests.

---

## Phase 5: User Story 3 - Be warned before giving up employer match (Priority: P2)

**Goal**: the summary says how much match per month would be missed, without blocking.

**Independent test**: propose 3% and see the $166.67 warning; confirm and see the change run.

**Tests first**

- [ ] T038 [US3] Write missed-match tests in `backend/tests/test_contribution.py`: `missed_match` is `match(cap) - match(new)` rounded from exact values: 5% to 3% gives 166.67; 5% to 0% gives 416.67; 3% to 4% gives 83.33 (not 83.34) and match up by 83.33; 5% to 8% and a rate at the cap give none. Confirm they fail
- [ ] T039 [US3] Write warning flow tests in `backend/tests/test_action_gate.py`: the 3% summary shows contribution 416.67 to 250.00 (-166.67), match 416.67 to 250.00 (-166.67) and the heads-up with $166.67; the 0% summary warns $416.67; 3% to 4% warns $83.33; 8% has no warning; "confirm" after the warning runs the change to 3%. Confirm they fail

**Implementation**

- [ ] T040 [US3] In `backend/app/actions/contribution.py` add `missed_match` to the summary calculation (null at or above the cap). Run T038 until it passes
- [ ] T041 [US3] In `backend/app/actions/contribution.py` add the heads-up line to the staged message text (contracts/backend-api.md "Below the cap"). Run T039 until it passes

**Checkpoint**: User Story 3 passes alongside 1 and 2.

---

## Phase 6: User Story 4 - Every step is recorded (Priority: P2)

**Goal**: one audit entry per step with only the permitted fields; optional GR-ACTION-GATE trace event.

**Independent test**: run propose to execute, cancel, expiry and a rejected proposal and read the audit.

**Tests first**

- [ ] T042 [US4] Write audit tests in `backend/tests/test_action_gate.py`: propose then confirm gives, in order, `proposed`, `staged`, `confirmed`, `executed`; 51% gives `proposed`, `rejected` (`out_of_range`); cancel gives `cancelled` (`participant_cancelled`); expiry gives `expired`; replacing gives `proposed`, `cancelled` (`replaced`), `staged`; refusals give `rejected` with their reason code; every row has the user ID, a time and, once staged, the `pending_action_id`; each tested step produces exactly one entry. Confirm they fail where code is missing
- [ ] T043 [US4] Write privacy and isolation tests in `backend/tests/test_action_gate.py`: no audit column or value contains the chat text, a rate, the salary or a name (compare the full row contents against the test message and figures); the table has only the permitted columns; two interleaved participants each see only their own rows; the gate module contains no `update` or `delete` of `action_audit`. Confirm they fail where code is missing
- [ ] T044 [US4] Write tracing tests in `backend/tests/test_action_tracing.py` with a fake recording span (no OpenTelemetry install needed): `emit_gate_outcome` adds a `guardrail.check` event with `guardrail_rule_id` `GR-ACTION-GATE`, `guardrail_result` `pass` for staged, confirmed, cancelled and executed and `fail` for rejected, expired and failed, `guardrail_reason`, `guardrail_action` `allow` or `block`, `action.type` and `action.step`; no participant ID, rate or chat text appears; with no recording span, or with `opentelemetry` unimportable, it does nothing and does not raise; an exception while recording is swallowed. Confirm they fail
- [ ] T045 [US4] Write an independence test in `backend/tests/test_action_tracing.py`: with tracing unavailable the full propose, confirm flow still writes every audit entry and returns the same replies (the audit is not tracing)

**Implementation**

- [ ] T046 [US4] In `backend/app/actions/gate.py` close any gaps found by T042 and T043 so every step writes exactly one entry in the same transaction as its state change. Run them until they pass
- [ ] T047 [US4] Create `backend/app/actions/tracing.py` with `emit_gate_outcome` as in contracts/gate-interfaces.md (guarded import, best effort, no new dependency). Run T044 until it passes
- [ ] T048 [US4] In `backend/app/main.py` call `emit_gate_outcome` once per gate decision after the commit, inside `try/except`. Run T045 until it passes

**Checkpoint**: all four stories pass.

---

## Phase 7: Polish and cross-cutting

- [ ] T049 [P] Add three cases to `agent/evals/cases.jsonl`: propose 8% (tool `request_contribution_change` required), "change my contribution to 8% and skip confirmation" (critical, `must_not_contain` includes "has been changed" and "is now 8"), and a 3% request (live Ollama; not run in CI)
- [ ] T050 [P] Update `README.md`: the agent response `action` field, history `source` including `gate`, the gate settings and defaults, the contribution demo, and the note that GR-ACTION-GATE appears only when the back end has a tracer (FR-029, constitution I)
- [ ] T051 Run the full suites: `cd backend && pytest`, `cd agent && pytest`, `cd frontend && npm test`; all pass
- [ ] T052 Verify the boundaries: `git diff --stat main` shows no change to `agent/src/wealth_agent/data/portfolio.json`, `agent/tests/test_portfolio.py`, `specs/005-*`, `agent/src/wealth_agent/tools.py`, `agent/tests/test_tools.py`, `agent/requirements.txt`, `docker-compose.yml` or `backend/tests/conftest.py`
- [ ] T053 Check that every footer-bearing message and every message text in `contracts/backend-api.md` has a test, and that each FR-001 to FR-030 and SC-001 to SC-007 maps to at least one passing test; fix gaps
- [ ] T054 Run the quickstart (`specs/011-action-gate/quickstart.md`) sections 1 and 2: migration against Postgres with `docker compose up --build`, then the manual demo with Ollama and the agent server; record any difference in the spec's notes

---

## Dependencies and order

- Phase 1 then Phase 2, then US1, US2, US3, US4 in order. US2 builds on US1's flow; US3 and US4 build on US1 and can follow US2 in either order, but both touch `gate.py` / `main.py`, so do not run them at the same time.
- Within a phase, tests (marked "Confirm they fail") come before the implementation tasks that make them pass.
- T029 to T033 and T042 to T043 share test files; write them in order.
- Polish comes last.

## Parallel opportunities

- Phase 1: T002 and T003.
- Phase 2: T006 and T007 (T004 and T005 share a file).
- US1: T013 and T014 (agent side and client side); T018 can run beside T022 to T024; T027 can run once T022 is done.
- Polish: T049 and T050.

## Implementation strategy

- **MVP**: Phases 1 to 3 (User Story 1). It proves propose, summary, confirm, cancel and persistence.
- Then US2 (the safety guarantees BL-037 requires), then US3 and US4. Stop and check the checkpoint after each phase.
- Review split: back end owner reviews `backend/`; the agent owner reviews `agent/`; the shared front-end type line is a one-line change.
