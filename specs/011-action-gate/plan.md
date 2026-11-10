# Implementation Plan: Action Gate for Agent Write Actions (Mock 401(k) Contribution Change)

**Branch**: `011-action-gate` | **Date**: 2026-11-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/011-action-gate/spec.md`

## Summary

Add a generic action gate to the back end: propose, check, stage, confirm, run, record. Use it for
one action, a mock 401(k) contribution change.

- The agent gets one new tool, `request_contribution_change`, which only reports what the
  participant asked for. The agent returns it as a new optional `action` field.
- The back end owns every decision: rules, the summary in dollars, staging with a 5-minute
  expiry, the one-time confirmation token, execution through a replaceable `ContributionService`,
  and an always-on audit record. State lives in Postgres through Alembic.
- "Confirm" and "cancel" are recognised in back-end code from the participant's own message,
  before the model is called. The model has no way to confirm, so "skip confirmation" can't work.
- Education-only mode blocks actions only; the agent's other behaviour is unchanged.
- The step-up hook is a FastAPI dependency that always passes today.
- When a tracer is present, each gate decision is also emitted as a `guardrail.check` event with
  rule ID `GR-ACTION-GATE`. Nothing depends on PR #11.

Key decisions are in [research.md](./research.md): R1 (gate in the back end), R2 (no participant ID
to the agent), R4 (confirm in code) and R11 (tracing).

## Technical Context

**Language/Version**: Python 3.12 for the back end; Python 3.10+ for the agent (3.11/3.12 locally); TypeScript for one type line in the shared front-end client.

**Primary Dependencies**: Existing only. Back end: FastAPI, SQLAlchemy 2 (sync), Alembic, psycopg 3, httpx. Agent: `strands-agents==1.63.0` (uses `@tool(context=True)`), `bedrock-agentcore`. `opentelemetry` is imported only if it is already installed (research R11). No new runtime dependency.

**Storage**: PostgreSQL. Migration `0005` adds `contributions`, `pending_actions` and `action_audit`, and widens `ck_messages_source`. The demo payroll seed is a read-only JSON file, `backend/app/data/payroll.json`.

**Testing**: `pytest` with in-memory SQLite, a fake agent (`monkeypatch` of `main.call_agent`), an injected clock, and overridden dependencies (`get_step_up_check`, `get_contribution_service`). Agent tool tests need no Ollama. Front end: the existing vitest suite.

**Target Platform**: The back end in Docker and locally; the agent through the local AgentCore runtime (`agent/agent.py`).

**Project Type**: Web service and agent in a monorepo (`backend/`, `agent/`, `frontend/`).

**Performance Goals**: A gate-only turn (confirm or cancel) makes no agent call and only a few indexed queries, so it is well under a second. A propose turn adds two or three queries to an existing agent turn.

**Constraints**: The gate's rules are enforced in code, not the prompt. One transaction per turn (constitution III). No UI changes. Do not modify `agent/src/wealth_agent/data/portfolio.json`, `agent/tests/test_portfolio.py` or `specs/005-*`. Nothing may depend on PR #11.

**Scale/Scope**: POC demo users. One action type. Five reason-bearing flows (propose, confirm, cancel, expire, fail).

## Constitution Check

*GATE: checked before Phase 0, and again after Phase 1 design (below).*

| Principle | Assessment | Result |
|---|---|---|
| **I. Contract-first** | Two additive changes, both written into the spec (FR-029) and contracts before code: the agent response gains an optional `action`, and history `source` gains the value `gate`. The request bodies are unchanged. Consumers named: the back-end agent client, the shared front-end type and the README. | PASS |
| **II. Graceful agent degradation** | Agent failure still falls back to mock with HTTP 200; mock replies never carry an `action`, so nothing is proposed. A malformed `action` is logged and ignored. Confirm and cancel don't need the agent. One deviation: a third `source` value, `gate` (Complexity Tracking). | PASS, with one justified deviation |
| **III. Persistence through Alembic** | New tables and the constraint change only through `0005`. Constraint and index names follow `app/db.py`. Each turn's writes (session, gate state, contribution, audit, both messages) are in one transaction. The exception is a follow-up transaction that records a failure after a rollback (Complexity Tracking). Read endpoints still write nothing; expiry is applied only on `POST /api/chat`. | PASS, with one justified deviation |
| **IV. Tests without external services** | Everything runs under `pytest` on SQLite with a fake agent and a fake clock. The partial unique index is created on SQLite too. Tracing is tested with a fake span. Each rule and error case has a test (FR-030). | PASS |
| **V. POC simplicity** | No new dependency, service or background job. Three small protocols (`ActionType`, `ContributionService`, `StepUpCheck`) are required by the spec (FR-002, FR-021, FR-012) and are justified in Complexity Tracking. Other action types are not built. | PASS, with justified abstractions |

**Post-design re-check (after Phase 1)**: Same result. The contracts and data model add no
fields, services or dependencies beyond those above.

## Project Structure

### Documentation (this feature)

```text
specs/011-action-gate/
├── spec.md                       # updated by this plan (see "Spec updates")
├── plan.md                       # this file
├── research.md                   # Phase 0
├── data-model.md                 # Phase 1
├── quickstart.md                 # Phase 1
├── contracts/
│   ├── agent-action.md           # back end ↔ agent: optional `action`
│   ├── backend-api.md            # history `source` adds `gate`; gate message texts
│   └── gate-interfaces.md        # ActionType, ContributionService, StepUpCheck, ActionGate, GR-ACTION-GATE
├── checklists/requirements.md
└── tasks.md                      # /speckit-tasks (not created here)
```

### Source Code: every file expected to change

Flags: **[PR #11]** means Kejiya's open PR plans to change the same file. **[PR #8]** means
Vinod's web sign-in PR changes the same file; it is merged into `009-sign-in-access-backend` but
is not on `main` yet (research R17).

```text
backend/
├── app/
│   ├── actions/                          NEW package
│   │   ├── __init__.py                   NEW
│   │   ├── gate.py                       NEW  ActionGate, reply classifier, settings, audit writes, token issue/redeem,
│   │   │                                      StepUpCheck + AlwaysPass, dependencies get_step_up_check / get_action_gate
│   │   ├── contribution.py               NEW  ContributionChange (ActionType), ContributionService + DemoContributionService,
│   │   │                                      seed loader, Decimal summary, message texts, get_contribution_service
│   │   └── tracing.py                    NEW  emit_gate_outcome (optional OpenTelemetry; no-op otherwise)
│   ├── data/payroll.json                 NEW  demo payroll seed (read-only)
│   ├── agent.py                          EDIT AgentReply.action; parse and validate the optional `action` field
│   ├── main.py                           EDIT chat(): classify reply before the agent call; propose after it;
│   │                                          _persist() runs the gate inside its transaction; source "gate";
│   │                                          HistoryMessage.source adds "gate"; emit tracing after commit
│   └── models.py                         EDIT Contribution, PendingAction, ActionAudit; ck_messages_source adds 'gate'
├── alembic/versions/0005_add_action_gate.py   NEW
└── tests/
    ├── test_action_gate.py               NEW  HTTP-level flow: every spec scenario and edge case
    ├── test_contribution.py              NEW  rules, Decimal figures, seed handling, service and token redemption
    ├── test_action_tracing.py            NEW  GR-ACTION-GATE with a fake span; no-op without one; a failure is swallowed
    └── test_agent.py                     EDIT parsing of the optional `action` (valid, absent, malformed)

agent/
├── agent.py                              EDIT [PR #11]  clear state before each turn; return `action` when set
├── src/wealth_agent/
│   ├── action_tools.py                   NEW  request_contribution_change handler + Strands @tool(context=True) wrapper
│   ├── agent.py                          EDIT [PR #11]  build_agent registers ACTION_TOOLS (one line)
│   └── prompts.py                        EDIT  guidance for the new tool; "never say a change was made"; bump PROMPT_VERSION
│                                               (PR #11 reads PROMPT_VERSION but doesn't edit this file)
├── tests/
│   ├── test_action_tools.py              NEW  handler validation; state recorded; no data changed
│   └── test_agent.py                     EDIT [PR #11]  expected tool list includes request_contribution_change
└── evals/cases.jsonl                     EDIT  3 cases: propose 8%; "skip confirmation" (critical); 3% below match

frontend/packages/core/src/api.ts         EDIT [PR #8]   HistoryMessage.source type adds "gate" (type only)

README.md                                 EDIT [PR #8] [PR #11]  agent contract `action`; history `source`;
                                               gate settings; contribution demo
.env.example                              EDIT [PR #8]   ACTION_* and CONTRIBUTION_* settings with demo defaults
```

Not changed, on purpose: `agent/src/wealth_agent/tools.py`, `agent/tests/test_tools.py` and
`agent/requirements.txt` (PR #11 owns them); `docker-compose.yml` (PR #8 changes it, and the defaults
are in code); `agent/src/wealth_agent/data/portfolio.json`; `agent/tests/test_portfolio.py`;
`specs/005-*`; `backend/tests/conftest.py` (gate fixtures live in the new test modules). PRs #9
and #10 share no files with this list.

**Structure Decision**: The gate is a new `backend/app/actions/` package beside `feedback.py` and
`entitlement.py`. The agent gets one new module. All existing layouts stay as they are.

## Phase 0: Research

Done. See [research.md](./research.md) (R1–R17); no open questions.

## Phase 1: Design

Done. See [data-model.md](./data-model.md), [contracts/](./contracts/) and [quickstart.md](./quickstart.md).

### Request flow in `POST /api/chat`

```text
existing checks (400, 401, 404 owner, 403 no access) → access, education_only
│
├─ gate.classify_reply(message)       read-only; then db.rollback() as today
│    CONFIRM / CANCEL / NOT_EXACT  ──►  no agent call
│                                       _persist(..., gate_step = handle_reply)      one transaction
│                                       source = "gate"
│    None  ──►  _reply_for() calls the agent (or the mock)
│               result.action?  yes ──► _persist(..., gate_step = handle_proposal)  one transaction
│                                       reply replaced by gate text, source = "gate"
│                               no  ──► _persist as today (source agent | mock)
│
└─ after commit: emit_gate_outcome() for each gate decision (best effort)
```

### Confirm, inside the transaction

1. Expire this participant's overdue pending changes.
2. Find the pending change for (participant, action type).
   - None: `nothing_pending`.
   - In another session: `other_session`.
3. Conditional update `pending → confirmed`. Zero rows means `already_handled`. Write the `confirmed` audit entry.
4. Re-read the current rate. If it differs from the snapshot: `stale`.
5. Issue the token (store its hash), then `StepUpCheck.verify`. A refusal rolls back and writes `step_up_required`.
6. `ActionType.execute`, which calls `ContributionService.apply_change(participant, new_rate, token)`, which redeems the token and upserts `contributions`.
7. Mark `executed` and write the audit entry. The result message becomes the reply.

If step 6 raises, roll back, then in a new transaction mark `failed`, write `confirmed` and `failed`
(`apply_failed`) audit entries and the two messages.

### Spec updates made with this plan

Plan decisions that change spec wording:

- Requested tidy: step-up wording is now "step-up authentication (method still to be decided)".
- FR-015 and FR-016: the participant ID comes only from the back end's verified token, and no ID is sent to the agent (research R2).
- FR-024: the store survives restarts of the agent and the back end.
- FR-029: names both contract changes and their consumers.
- Assumptions: the gate and store live in the back end, and the seed is at `backend/app/data/payroll.json`.
- Edge case: confirm and cancel still work when the agent is down.
- New edge case: a stale snapshot.

### Gate message footer

Every message written by the gate (staged summary, executed, cancelled, expired, every refusal)
ends with its own last line, added in code by one helper: `Demo data: no real account was changed.`
The footer is not part of the message texts in `contracts/backend-api.md`; the helper appends it
after a blank line. Replies that come from the model are not given this line. The "(Demo data
only.)" and "This changed demo data only." phrases inside the staged and executed texts are removed
to avoid repeating it. A test checks that every gate message ends with exactly this line, once.

### Agent prompt change (prompts.py)

Add guidance for the new tool to the system prompt: when the participant asks to change their
401(k) contribution rate, call `request_contribution_change` with the number they asked for; never
say a change has been made, because the system shows the summary and asks them to confirm. The
existing "cannot place trades, move money or change any account" boundary stays, with the
contribution request named as the one thing the agent can pass on. Bump `PROMPT_VERSION`.
Education-only handling in the agent is unchanged.

## Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| `messages.source` gains `gate` (Principle II names `agent` and `mock`) | Gate text is neither model output nor a mock. Principle II exists so the origin of each assistant message is recorded truthfully | Labelling it `agent` misattributes code-written outcomes; `mock` hides real outcomes; `NULL` breaks Principle II |
| A follow-up transaction after a failed apply (Principle III: writes that belong together are committed together) | The failure must be recorded even though the main write rolled back | Writing nothing would lose the `failed` record that FR-025 requires |
| Three protocols: `ActionType`, `ContributionService`, `StepUpCheck` (Principle V: justify abstractions) | Required by the spec: a generic gate (FR-002), a replaceable contribution source (FR-021) and a step-up hook (FR-012). Each is a few lines | Hard-coding the contribution flow would mean rewriting the gate for every later action and for Principal's systems |

## Risks

| Risk | Mitigation |
|---|---|
| The local model doesn't call the tool reliably | Eval cases for proposing and for "skip confirmation" (critical). The gate's guarantees don't depend on the model. The worst case is that no summary appears and nothing is staged |
| The model's free text claims success | Whenever an `action` is present, the gate replaces the reply. The prompt forbids claims of success. An eval `must_not_contain` checks phrases such as "has been changed" |
| GR-ACTION-GATE is invisible until the back end has a tracer | Documented (research R11). The audit record is the business record and doesn't depend on tracing |
| Merge friction with PR #11 and PR #8 | Small, separate hunks. The new tool is in its own module; `tools.py`, `requirements.txt` and `docker-compose.yml` are untouched |
| The partial unique index behaves differently on SQLite | SQLAlchemy emits `WHERE` on both; a test asserts that a second pending row is refused |
