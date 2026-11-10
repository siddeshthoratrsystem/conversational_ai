# Research: Action Gate (spec 011)

Each decision records what was chosen, why, and what else was considered. There are no open
NEEDS CLARIFICATION items.

## R1. Where the gate runs: in the back end

**Decision**: The gate, its state and the audit record live in the back end (`backend/app/actions/`),
next to the token check and the Postgres store. The agent never stages, confirms or runs anything.
It only reports that the participant asked for a change (R3).

**Rationale**:
- The back end is where the participant's identity is verified (specs 008/009), so the gate gets
  the participant ID from the token directly, not from another service (FR-014).
- The back end already has the per-user Postgres store, Alembic, one-transaction writes and a
  pytest setup with in-memory SQLite (constitution III and IV). That is the preference given for
  this plan.
- The back end already decides education-only mode (`access == "unavailable"`), so FR-011 needs no
  agent change. This fits the decision to honour the flag for actions only.
- The agent keeps conversations in process per `session_id` and loses them on restart
  (`agent/agent.py`). Pending changes must survive restarts (FR-024), and the back end store already does.
- Confirm and cancel replies can be handled in code before the model is called (R4). So the model
  has no confirm tool to call, misuse or be talked into calling.

**Alternatives considered**:
- *Gate in the agent with its own store (SQLite or JSON file)*: a second persistence pattern
  without Alembic, plus a new way to pass and trust the participant ID. Rejected.
- *Gate in the agent, calling a new internal back-end API for state*: adds an endpoint and
  service-to-service authentication, and splits one decision across two services. Rejected.
- *Gate in the agent with direct Postgres access*: gives the agent `DATABASE_URL` and the back
  end's schema. This breaks the component boundary in the constitution. Rejected.

## R2. How the agent receives the signed-in participant's ID: it doesn't need to

**Decision**: No participant ID is sent to the agent. The back-end-to-agent request stays
`{prompt, session_id, education_only?}`. The gate uses `current_user` (the verified token's `sub`).

**Rationale**: R1 puts every identity-dependent decision in the back end. Sending the ID anyway
would add a contract field nothing uses (constitution V) and personal data to another service.

**Consequence for the spec**: FR-015 and FR-016 are reworded. The back end takes the participant
ID only from the verified token; the gate refuses any action without one, which is a defensive
check because `current_user` already returns 401 without a token. If a later agent-side action
needs the ID, it is added then as an optional field (constitution I).

## R3. How a proposal travels from the agent to the back end

**Decision**: A new agent tool, `request_contribution_change(new_rate_pct)`, checks only that the
argument is a finite number. It records `{"type": "contribution_change", "params": {"new_rate_pct": n}}`
on the agent's per-session state and tells the model the system will ask the participant to confirm.
The AgentCore entrypoint clears that state before each turn and, if it is set afterwards, returns
it as a new optional `action` field next to `reply` and `intent`. If the model calls the tool more
than once in a turn, the last call wins.

**Rationale**:
- Strands 1.63 supports `@tool(context=True)` with `tool_context.agent.state` (checked in
  `agent/.venv`), so no global or thread-local state is needed.
- The tool changes nothing, so spec 005's code-level guarantee (no agent tool modifies data) still
  holds. The impact note in the spec still applies, because the system as a whole now writes data.
- All rules (range, whole number, different from current) are checked once, in the back end, so
  there is a single authority and nothing is duplicated in the agent.

**Alternatives considered**: parsing the model's reply text (unreliable); reusing `intent`
(a plain string, reserved for intent classification); a confirm tool for the model (exactly what
BL-037 forbids).

## R4. Recognising "confirm" and "cancel" in code

**Decision**: Before calling the agent, the back end normalises the participant's message (trim,
lower-case, strip surrounding punctuation). Then:

| Message | Pending change in this chat | Pending only in another chat | Nothing pending |
|---|---|---|---|
| Exactly an accepted confirm reply | confirm (R5) | refuse: "only in the chat where it was proposed" | refuse: "nothing to confirm" |
| Exactly an accepted cancel reply | cancel | refuse: same as above | refuse: "nothing to cancel" |
| Starts with a confirm or cancel word, plus more text | refuse: "reply exactly confirm or cancel; to change the rate, ask for the new rate" | goes to the agent | goes to the agent |
| Anything else | goes to the agent; the change stays pending | goes to the agent | goes to the agent |

Every refusal is recorded as `rejected` with a reason code (data-model.md). Accepted replies are
settings (`ACTION_CONFIRM_REPLIES`, default `confirm`; `ACTION_CANCEL_REPLIES`, default `cancel`).

**Rationale**: This enforces FR-005 and FR-006 in code. The confirmation is always the
participant's own message, in a later request than the summary, in the same chat, and the model
is never involved. "Skip confirmation" and "confirm, but make it 9%" cannot run anything.

## R5. Confirmation token

**Decision**: On a valid confirm, the gate issues a token: 32 random bytes from `secrets`. Only its
SHA-256 hash is stored, on the staged change. The token goes to
`ContributionService.apply_change(participant_id, staged_change, token)`. The service redeems the
token through the gate's `redeem()`, which in one conditional update checks that the token matches
the staged change, belongs to the same participant and chat session, is unused and not expired,
and marks it used. A second redemption fails.

**Rationale**: Execution requires the token (FR-007), and reuse and cross-participant use fail at
the point of execution, not only in the chat handler. A future Principal-backed service would
redeem the same way and can send the staged change ID as an idempotency key. The token never
leaves the back-end process: it is not returned to the browser or the model.

## R6. Persistence: Postgres through Alembic

**Decision**: Migration `0005_add_action_gate.py` adds three tables (`contributions`,
`pending_actions`, `action_audit`) and widens `ck_messages_source` to allow `'gate'` (R9). Details
are in data-model.md.

- At most one pending change per participant and action type, enforced by a partial unique index
  (`WHERE status = 'pending'`). SQLAlchemy creates it on Postgres and SQLite, so tests cover it.
- `params` is a JSON column. Only the action type reads it.
- Each turn writes everything in one transaction: the session row (if new), gate state changes,
  the contribution update, audit entries, and the user and assistant messages (constitution III).
  The existing `_persist` gains an optional callback that runs inside its transaction, after the
  session row is flushed, and returns the reply text.

**Exception**: when applying a change fails, the transaction is rolled back. A second transaction
then marks the staged change `failed` and writes the `failed` audit entry and the two messages.
That is the only way to record a failure that rolled back the main write.

## R7. Expiry

**Decision**: `expires_at = staged_at + ACTION_EXPIRY_SECONDS` (default 300). Expiry is checked
whenever the gate runs for a participant, inside the turn's transaction: pending changes past
`expires_at` are marked `expired` and get an `expired` audit entry before anything else happens.
`redeem()` also refuses an expired token. Tests pass in a clock function instead of sleeping.

**Rationale**: No background job is needed (constitution V), and an expired change can never run,
whether or not it was noticed yet.

## R8. Concurrency (two tabs confirming at once)

**Decision**: Confirm moves the row from `pending` to `confirmed` with a conditional update
(`WHERE id = :id AND status = 'pending'`). It continues only if exactly one row changed. On
Postgres the second request waits for the row lock, then sees zero rows and gets "already
handled". Token redemption has the same shape. A new proposal that races another proposal hits
the partial unique index; `_persist` already retries once on `IntegrityError`, and the retry
cancels the pending change it now finds.

## R9. Message `source` for gate replies

**Decision**: Assistant messages whose text comes from the gate are stored with `source = 'gate'`.
That covers every confirm, cancel or refusal turn, and propose turns where the gate replaced the
model's reply. When the agent was called, `latency_ms` is still recorded. The history response's
`source` type widens to `agent | mock | gate | null`, and the shared front-end type in
`frontend/packages/core/src/api.ts` widens to match. No UI code reads `source`, so nothing renders
differently.

**Rationale**: Constitution II says every assistant message records where its text came from, so
mock data stays separate from agent data. Labelling gate text `agent` would be wrong, and
labelling it `mock` would hide real outcomes. This is listed in Complexity Tracking because
Principle II names only `agent` and `mock`.

**Alternatives considered**: `source = NULL` (breaks Principle II); a new `origin` column (more
schema change for the same information).

## R10. Disclaimer on gate messages

**Decision**: Gate messages do not carry spec 005's investment disclaimer. They are system
statements about a demo change, not answers, and each one says that it uses demo data.

**Rationale**: Spec 005 FR-005 applies to agent answers, and the agent's own replies still get it.
Appending it to "Your contribution is now 8%" would read as noise. Spec 005 is unchanged.

## R11. GR-ACTION-GATE tracing, independent of PR #11

**Decision**: `backend/app/actions/tracing.py` has one function, `emit_gate_outcome(step, result, reason, action_type)`.
It tries to import `opentelemetry.trace`. If the import works and `trace.get_current_span().is_recording()`
is true, it adds a `guardrail.check` event matching PR #11's event contract:

| Attribute | Value |
|---|---|
| `guardrail_rule_id` | `GR-ACTION-GATE` |
| `guardrail_result` | `pass` (staged, confirmed, cancelled, executed) or `fail` (rejected, expired, failed) |
| `guardrail_reason` | the reason code, for example `out_of_range` (never values or personal data) |
| `guardrail_action` | `allow` or `block` |
| `action.type`, `action.step` | for example `contribution_change`, `staged` |

Otherwise it does nothing. It is called after the turn's transaction commits, inside `try/except`,
so tracing can never change a gate outcome or a reply. The participant ID is never sent, which
follows PR #11 ("no multi-tenant identity in traces").

**Rationale**:
- No new dependency: if OpenTelemetry isn't installed, or no tracer provider is configured, the
  OpenTelemetry API returns a non-recording span and the function returns. This is the same
  "tracing off" behaviour PR #11 describes.
- Nothing depends on PR #11. Tests swap in a fake recording span, so they run whether or not
  `opentelemetry` is installed.

**Limitation**: PR #11 configures tracing in the agent process only; back-end spans are its
future work. GR-ACTION-GATE therefore appears in traces only once the back end has a tracer (from
PR #11's follow-up, or an `opentelemetry-instrument` run of the back end). Until then the audit
record (R12) is the only record, which is by design.

**For PR #11's owner** (additive, not required): `GR-ACTION-GATE` as a third rule ID and `block`
as a `guardrail_action` value in `trace-schema.md`.

## R12. The audit record is the business record, not tracing

**Decision**: `action_audit` rows are always written, in the same transaction as the state change
they describe (R6), whatever the tracing setting. The app only inserts audit rows; it never
updates or deletes them. Each row has the participant ID, time, action type, staged-change ID
(when one exists), step and reason code, and nothing else (FR-025). Rates, chat text, names and
salary are not in the audit. The rates live on the staged change the row points to.

## R13. Step-up hook

**Decision**: A `StepUpCheck` protocol with `verify(participant_id, action_type, claims) -> bool`.
It runs after the token is issued and before `apply_change` redeems it. It is provided by the FastAPI dependency
`get_step_up_check`, which returns `AlwaysPass` today. Tests override the dependency with a
refusing check, the same way `get_verifier` is overridden in `conftest.py`. If the check refuses,
the confirm transaction rolls back, so nothing is run or used up. The change stays pending until it
expires. A `rejected` entry with reason `step_up_required` is written in a follow-up transaction,
the same shape as the failure path in R6.

## R14. Demo payroll seed location

**Decision**: `backend/app/data/payroll.json`, read once and cached. The spec only suggested a path
under `agent/`. The back end owns the gate, and the back-end image copies only `backend/app`.

```json
{ "currency": "USD", "annual_salary": 100000,
  "employer_match": { "match_pct": 100, "cap_pct_of_pay": 5 },
  "starting_contribution_pct": 5,
  "note": "Demo data, the same for every participant. Not Principal policy." }
```

A missing or invalid file makes the contribution action unavailable. Proposals get a plain
message and are recorded as `rejected` with reason `seed_unavailable`.

## R15. Money arithmetic

**Decision**: Use `decimal.Decimal`. `monthly_pay = salary / 12`. For each rate,
`contribution = monthly_pay × rate / 100` and `match = monthly_pay × min(rate, cap) / 100 × match_pct / 100`.
Each displayed amount, including each difference and the missed-match amount
(`match(cap) − match(new)`), is computed from exact values and then rounded half-up to cents
(FR-019). Checked against the spec: 5%→8% gives +$250.00 with the match unchanged at $416.67;
5%→3% gives −$166.67 with $166.67 of match missed; 3%→4% gives +$83.33 with $83.33 still missed;
0% misses $416.67.

## R16. Generic gate and its settings

**Decision**: The generic part is a small `ActionType` protocol (data-model.md and
contracts/gate-interfaces.md) and a registry dictionary of action types. The gate drives the
propose, check, stage, confirm, run and record flow; each action type supplies `parse`, `check`,
`summary`, `result_message` and `execute`. Only `ContributionChange` is registered.

Settings come from environment variables, with demo defaults in code, so `docker-compose.yml`
does not change:

| Variable | Default |
|---|---|
| `ACTION_EXPIRY_SECONDS` | `300` |
| `ACTION_CONFIRM_REPLIES` | `confirm` (comma-separated) |
| `ACTION_CANCEL_REPLIES` | `cancel` |
| `CONTRIBUTION_MIN_PCT` / `CONTRIBUTION_MAX_PCT` | `0` / `50` |
| `CONTRIBUTION_WHOLE_PCT_ONLY` | `true` |

## R17. Keeping clear of the open pull requests

- **PR #11 (Kejiya, spec 010 tracing)** plans changes to `agent/agent.py`,
  `agent/src/wealth_agent/agent.py`, `agent/src/wealth_agent/tools.py`, `agent/tests/test_agent.py`,
  `agent/tests/test_tools.py`, `agent/requirements.txt`, `agent/pyproject.toml` and `README.md`.
  To limit overlap, the new tool goes in a new module (`action_tools.py`) and its tests in a new
  file, and `tools.py` and `test_tools.py` are not edited. Overlaps that remain: a few lines in
  `agent/agent.py`, one line in `agent/src/wealth_agent/agent.py`, one expected-list line in
  `agent/tests/test_agent.py`, and `README.md`. All are small, separate hunks.
- **PR #8 (Vinod, web sign-in)** shows as merged, but into `009-sign-in-access-backend` 28 seconds
  after that branch was merged to `main` (PR #7). Its changes are not on `main`. It touches
  `README.md`, `.env.example` and `frontend/packages/core/src/api.ts`, which this plan also
  changes. When PR #8's work is re-raised against `main`, expect small conflicts in those three files.
- PRs #9 and #10 (test framework, CI gate) share no files with this plan.
