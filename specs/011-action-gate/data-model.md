# Data Model: Action Gate (spec 011, revision 3)

All tables are added by Alembic migration `backend/alembic/versions/0005_add_action_gate.py` and
mirrored in `backend/app/models.py`. Names follow the naming convention in `app/db.py`; check
constraints are named explicitly, as `ck_messages_*` already are. Times are `timestamptz`, in UTC.

## Who reads and writes what

| Table | Schema owner | Written by | Read by |
|---|---|---|---|
| `contributions`, `pending_actions`, `action_audit` | Back end (Alembic 0005, `backend/app/models.py`) | Agent runtime only (`agent/src/wealth_agent/actions/`) | Agent runtime only |
| `sessions` | Back end | Back end only, created before the agent is called | Back end; the agent relies on it only through the FK |
| `messages` | Back end | Back end only | Back end only |

The agent reaches the gate tables through `DATABASE_URL`, with table definitions in
`agent/src/wealth_agent/actions/store.py` that mirror `backend/app/models.py`.
`backend/tests/test_agent_store_schema.py` keeps the two in step (research R21). The agent never
creates or alters tables; agent tests create them on in-memory SQLite only. Every gate statement,
reads included, runs in a transaction under `SET LOCAL statement_timeout = ACTION_DB_TIMEOUT_SECONDS`
(default 3 s) on Postgres.

### Which record is authoritative

`action_audit`, with `pending_actions` and `contributions`, is the authoritative record of gate
steps. The agent commits these before it replies. The back end stores the chat messages afterwards,
in its own transaction. If that fails, or the back end gives up waiting:
- the gate's state and audit are still correct;
- the chat history lacks that turn;
- the agent's in-process conversation has it.

Nothing reconciles the two. For the POC, the audit is what a reviewer reads.

## `contributions`: a participant's current contribution rate

| Column | Type | Notes |
|---|---|---|
| `user_id` | text, PK | Token `sub` |
| `rate_pct` | integer, not null | Check `ck_contributions_rate_pct`: `rate_pct BETWEEN 0 AND 100` (a storage sanity bound; the demo range is a setting) |
| `updated_at` | timestamptz, not null | Set when an executed change writes the row |

- No row means the participant is still at the seed's `starting_contribution_pct` (FR-023).
- Written only by the agent's `DemoContributionService.apply_change`, after a token is redeemed.

## `pending_actions`: staged changes

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity, PK | The staged-change reference used in the audit |
| `user_id` | text, not null, indexed | Owner (token `sub`) |
| `session_id` | text, FK `sessions.id`, not null | The chat where it was staged; confirm only here. The back end creates the `sessions` row before calling the agent (research R6, R20) |
| `action_type` | text, not null | For example `contribution_change` |
| `params` | JSON, not null | Exact values to run, for example `{"new_rate_pct": 8}` |
| `snapshot` | JSON, not null | Values the summary was based on, for example `{"current_rate_pct": 5}` |
| `status` | text, not null | Check `ck_pending_actions_status`: `pending`, `confirmed`, `executed`, `cancelled`, `expired` or `failed` |
| `staged_at` | timestamptz, not null | When the gate wrote the row, at the end of turn 1 |
| `expires_at` | timestamptz, not null | `staged_at + ACTION_EXPIRY_SECONDS` |
| `token_hash` | text, null | SHA-256 of the confirmation token, set at confirm |
| `token_used_at` | timestamptz, null | Set when the token is redeemed; a second redemption fails |
| `closed_at` | timestamptz, null | When the change left `pending` |

Indexes:
- `uq_pending_actions_one_pending`: unique on (`user_id`, `action_type`) `WHERE status = 'pending'`.
  At most one pending change per participant and action type (FR-010).
- `ix_pending_actions_user_id`.

Turn 2 finds turn 1's change only through this table: `user_id` = the verified `sub`,
`session_id` = this chat, `status = 'pending'`, `expires_at` in the future.

### State transitions

```text
 end of turn 1, within the deadline
        │                ┌──────────── exact "cancel" / replaced by a newer staged change ──► cancelled
        ▼                │
    (staged) ─► pending ─┼─── now > expires_at (noticed on the participant's next turn) ────► expired
                         │
                         └─ exact "confirm" (same participant, same chat, not expired) ─► confirmed
                                                                                            │
                                 step-up refuses ─► rollback (stays pending) ◄──────────────┤
                                 apply_change fails ─► failed ◄─────────────────────────────┤
                                 database timeout ─► rollback (stays pending) ◄─────────────┤
                                 token redeemed + rate written ─► executed ◄────────────────┘
```

- A request that was only held in turn 1 (too slow, write failed, or rejected) never creates a row.
- `confirmed` lasts only within one transaction: it ends as `executed`, rolls back to `pending`, or
  becomes `failed` in the follow-up transaction.
- `executed`, `cancelled`, `expired` and `failed` are final.
- The current rate is re-checked at confirm. If it changed since staging, the change is refused
  (`stale`).

## `action_audit`: the authoritative record (always on, append-only)

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity, PK | |
| `user_id` | text, not null, indexed | Participant ID; the only personal data |
| `action_type` | text, not null | |
| `pending_action_id` | bigint, FK `pending_actions.id`, null | The staged change |
| `step` | text, not null | Check `ck_action_audit_step`: `staged`, `rejected`, `confirmed`, `cancelled`, `expired`, `executed` or `failed` (revision 3 removes `proposed`) |
| `reason` | text, null | Reason code (below); no free text |
| `created_at` | timestamptz, not null, default now | |

There is no chat text, rate, salary or name (FR-025). The app only inserts rows. `staged` means the
gate wrote the pending change. It does not claim the participant saw the summary. A `rejected` row
for a turn-1 request has no `pending_action_id`, because no pending change is written.

### Steps written per flow

| Flow | Audit entries, in order |
|---|---|
| Held and staged within the deadline | `staged` |
| Staged, replacing a pending one | `cancelled` (old, `replaced`), `staged` (new) |
| Rejected by the policy in turn 1 | `rejected` with the reason, no `pending_action_id`, written at the end of the turn within the deadline (one row per rejected call). The reason also goes to the model |
| Held or rejected, but past the deadline or the write failed | none (logged and traced: `too_slow`, `store_failed`) |
| Exact confirm | `confirmed`, `executed` |
| Confirm, apply fails | `confirmed` and `failed` (`apply_failed`) (follow-up transaction) |
| Confirm, step-up refuses | `confirmed` and `rejected` (`step_up_required`) (follow-up transaction); stays pending |
| Confirm, lost a race or stale | `rejected` (`already_handled` or `stale`) |
| Exact confirm or cancel while education-only or without `ai_planning` | `rejected` (`education_only`); stays pending |
| Exact cancel | `cancelled` (`participant_cancelled`) |
| Expiry noticed | `expired` |
| Confirm or cancel with extra words, change pending in this chat | `rejected` (`not_exact_reply`), with that change's ID; stays pending |
| Confirm or cancel, nothing pending here, pending in another chat of this participant | `rejected` (`other_session`), with that change's ID; stays pending |
| Confirm or cancel, nothing pending | `rejected` (`nothing_pending`) |
| Confirm or cancel message without a valid token | none; reply "Your sign-in has expired. Please sign in again, then reply confirm or cancel."; model not called; logged and traced with the case (`sign_in_token_missing`, `sign_in_token_expired` or `sign_in_token_invalid`) |
| Confirm or cancel message with actions disabled at start-up, or the store unreadable | none; reply "Contribution changes aren't available right now."; model not called; logged and traced (`actions_unavailable`, `store_failed`) |
| Any other message without a valid token or with actions disabled | none (goes to the model; the tool refuses; logged and traced) |

### Reason codes

| Code | Where it appears | When |
|---|---|---|
| `out_of_range` | returned to the model; recorded | Rate outside `CONTRIBUTION_MIN_PCT`–`CONTRIBUTION_MAX_PCT` |
| `not_whole_pct` | returned to the model; recorded | Rate has a fraction (fixed rule) |
| `invalid_params` | returned to the model; recorded | Missing or unknown parameters after the tool's number check |
| `same_as_current` | returned to the model; recorded | New rate equals the current rate |
| `seed_unavailable` | returned to the model; recorded | Demo payroll seed missing or invalid |
| `unknown_action` | returned to the model; recorded | No policy registered under that name |
| `education_only` | returned to the model and recorded (turn 1); recorded (turn 2) | Education-only flag, or `ai_planning` not `true` |
| `no_verified_participant` | returned to the model, or the sign-in reply for a confirm or cancel message; logged and traced | No verified token this turn |
| `actions_unavailable` | returned to the model, or the "isn't available" reply for a confirm or cancel message; logged and traced | Actions disabled at start-up, or the tool ran outside `run_turn` |
| `sign_in_token_missing` | logged and traced only | The request had no usable `Authorization: Bearer` header |
| `sign_in_token_expired` | logged and traced only | The sign-in token's `exp` has passed (beyond the 60 s leeway) |
| `sign_in_token_invalid` | logged and traced only | The sign-in token is bad: signature, issuer, audience, algorithm, `sub` or format. Not the same as `token_invalid`, and never written to the audit |
| `too_slow` | logged and traced | The turn passed `ACTION_STAGE_DEADLINE_SECONDS` before its end-of-turn writes |
| `store_failed` | logged and traced; "isn't available" reply for a confirm or cancel message when a pre-model read fails | An end-of-turn write (staging or rejection rows) or a pre-model read failed or timed out (`ACTION_DB_TIMEOUT_SECONDS`) |
| `not_exact_reply` | recorded | Confirm or cancel with extra words while a change is pending in this chat |
| `other_session` | recorded | Confirm or cancel here while the change is pending in another chat |
| `nothing_pending` | recorded | Confirm or cancel with nothing pending |
| `replaced` | recorded | Pending change replaced by a newer staged one |
| `participant_cancelled` | recorded | Exact cancel |
| `expired` | recorded (step `expired`) | Noticed after `expires_at` |
| `already_handled` | recorded | Lost a confirm race, or the token was already used |
| `token_invalid` | recorded | A confirmation token was refused: it belongs to another participant, chat or change |
| `step_up_required` | recorded | Step-up check refused |
| `stale` | recorded | Current rate changed since staging |
| `apply_failed` | recorded | The contribution source failed to apply the change |

Every code is also sent as `guardrail_reason` in the optional GR-ACTION-GATE trace event (research R11).

## `messages.source` (existing column, widened)

`ck_messages_source` changes from `source IN ('agent', 'mock')` to
`source IN ('agent', 'mock', 'gate')`. The migration drops and recreates it. Turn-1 rejection
explanations are model text and stored as `agent`.

## Demo payroll seed (file, read-only)

`agent/src/wealth_agent/data/payroll.json`: `currency`, `annual_salary`, `employer_match.match_pct`,
`employer_match.cap_pct_of_pay`, `starting_contribution_pct` and `note`. Loaded once by
`contribution_service.py` and validated: positive salary, percentages from 0 to 100, and a starting
rate within the configured range.

## In-process types (not stored)

- **`Participant`**: verified `sub` and claims, for one turn. Never stored, logged or put in the conversation.
- **`TurnContext`** (`agent.state["action_turn"]`): `participant_id`, `session_id`, `allowed`. Set by `run_turn` around the model call. It lives on the Strands agent that `agent_for` returns for exactly one (participant, chat session) pair, so two participants or two chats never share it. A request without a verified participant gets a fresh, empty agent that is not stored, so it has no conversation to keep and shares nothing.
- **`HeldAction`** (`agent.state["held_action"]`): `type` and parsed `params` after a passing policy check; the last one wins.
- **`RejectedAction`** (`agent.state["rejected_actions"]`): a list of `type` and `reason`, one per rejected call, recorded at the end of the turn.
- Turn memory (`action_turn`, `held_action`, `rejected_actions`) is cleared at the start and end of every turn, including when the model raises. It is never stored.
- **`CheckResult`**: `held` or `rejected` with `reason` and the plain `message` the tool returns to the model.
- **`GateResult`**: `step`, `reason`, `reply_text`, `pending_action_id`. `reply_text` becomes the reply with `source: "gate"`; the same text without the footer goes into the conversation.
- **`ContributionSummary`**: current and new rate, before and after amounts and differences for contribution and match, and `missed_match` (null at or above the cap). `Decimal` values rounded to cents.
- **`ConfirmationToken`**: raw token (never stored), `pending_action_id`, `user_id`, `session_id`.
