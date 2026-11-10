# Data Model: Action Gate (spec 011)

All tables are added by Alembic migration `backend/alembic/versions/0005_add_action_gate.py` and
mirrored in `backend/app/models.py`. Names follow the naming convention in `app/db.py`; check
constraints are named explicitly, as `ck_messages_*` already are. Times are `timestamptz`, in UTC.

## `contributions`: a participant's current contribution rate

| Column | Type | Notes |
|---|---|---|
| `user_id` | text, PK | Token `sub` |
| `rate_pct` | integer, not null | Check `ck_contributions_rate_pct`: `rate_pct BETWEEN 0 AND 100` (a storage sanity bound; the demo range is a setting) |
| `updated_at` | timestamptz, not null | Set when an executed change writes the row |

- No row means the participant is still at the seed's `starting_contribution_pct` (FR-023).
- Written only by `DemoContributionService.apply_change`, after a token is redeemed.

## `pending_actions`: staged changes

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity, PK | The staged-change reference used in the audit |
| `user_id` | text, not null, indexed | Owner |
| `session_id` | text, FK `sessions.id`, not null | The chat where it was proposed; confirm only here |
| `action_type` | text, not null | For example `contribution_change` |
| `params` | JSON, not null | Exact values to run, for example `{"new_rate_pct": 8}` |
| `snapshot` | JSON, not null | Values the summary was based on, for example `{"current_rate_pct": 5}` |
| `status` | text, not null | Check `ck_pending_actions_status`: `pending`, `confirmed`, `executed`, `cancelled`, `expired` or `failed` |
| `staged_at` | timestamptz, not null | |
| `expires_at` | timestamptz, not null | `staged_at + ACTION_EXPIRY_SECONDS` |
| `token_hash` | text, null | SHA-256 of the confirmation token, set at confirm |
| `token_used_at` | timestamptz, null | Set when the token is redeemed; a second redemption fails |
| `closed_at` | timestamptz, null | When the change left `pending` |

Indexes:
- `uq_pending_actions_one_pending`: unique on (`user_id`, `action_type`) `WHERE status = 'pending'`.
  At most one pending change per participant and action type (FR-010).
- `ix_pending_actions_user_id`.

### State transitions

```text
                 ┌──────────── cancel reply / replaced by a new proposal ───────► cancelled
                 │
 (staged) ─► pending ─── now > expires_at (checked on next gate run) ──────────► expired
                 │
                 └─ confirm reply (same user, same chat, not expired) ─► confirmed
                                                                            │
                         step-up refuses ─► rollback (stays pending) ◄──────┤
                         apply_change fails ─► failed ◄─────────────────────┤
                         token redeemed + rate written ─► executed ◄────────┘
```

- `confirmed` only lasts within one transaction: it ends that same transaction as `executed`,
  rolls back to `pending` (step-up refusal), or becomes `failed` in the follow-up transaction (research R6, R13).
- `executed`, `cancelled`, `expired` and `failed` are final.
- The participant's current rate is re-checked at confirm time. If it changed since staging, which
  is impossible today but possible with a real recordkeeper, the change is refused (`stale`) and
  must be proposed again.

## `action_audit`: the business record (always on, append-only)

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity, PK | |
| `user_id` | text, not null, indexed | Participant ID; the only personal data |
| `action_type` | text, not null | |
| `pending_action_id` | bigint, FK `pending_actions.id`, null | Null for steps before anything was staged |
| `step` | text, not null | Check `ck_action_audit_step`: `proposed`, `rejected`, `staged`, `confirmed`, `cancelled`, `expired`, `executed` or `failed` |
| `reason` | text, null | Reason code (below); no free text |
| `created_at` | timestamptz, not null, default now | |

There is no chat text, no rate, no salary and no name (FR-025). The app only inserts rows.

### Steps written per flow

| Flow | Audit entries, in order |
|---|---|
| Valid proposal | `proposed`, `staged` |
| Proposal replacing a pending one | `proposed`, `cancelled` (old, `replaced`), `staged` (new) |
| Invalid proposal | `proposed`, `rejected` (reason) |
| Confirm | `confirmed`, `executed` |
| Confirm, apply fails | `confirmed` and `failed` (follow-up transaction, research R6) |
| Confirm, step-up refuses | `confirmed` and `rejected` (`step_up_required`) (follow-up transaction, research R13); the change stays pending |
| Cancel | `cancelled` (`participant_cancelled`) |
| Expiry noticed | `expired` |
| Refused confirm or cancel | `rejected` (reason) |

### Reason codes

| Code | When |
|---|---|
| `out_of_range` | Rate outside `CONTRIBUTION_MIN_PCT`–`CONTRIBUTION_MAX_PCT` |
| `not_whole_pct` | Rate has a fraction and whole percentages are required |
| `invalid_params` | Missing, unknown or non-numeric parameters |
| `same_as_current` | New rate equals the current rate |
| `education_only` | Chat is in education-only mode |
| `no_participant` | No verified participant ID |
| `seed_unavailable` | Demo payroll seed missing or invalid |
| `unknown_action` | Action type not registered |
| `nothing_pending` | Confirm or cancel with no pending change |
| `other_session` | Confirm or cancel from a chat other than the proposing one |
| `not_exact_reply` | Reply starts with confirm or cancel but has more text |
| `expired` | Confirm after expiry (also written with step `expired`) |
| `already_handled` | Lost a confirm race, or the token was already used |
| `token_invalid` | Token missing, wrong participant, wrong session or wrong change |
| `step_up_required` | Step-up check refused |
| `stale` | Current rate changed since staging |
| `replaced` | Pending change replaced by a new proposal |
| `participant_cancelled` | Participant replied cancel |
| `apply_failed` | The contribution source failed to apply the change |

## `messages.source` (existing column, widened)

`ck_messages_source` changes from `source IN ('agent', 'mock')` to
`source IN ('agent', 'mock', 'gate')`. The migration drops and recreates it. See research R9.

## Demo payroll seed (file, read-only)

`backend/app/data/payroll.json`: `currency`, `annual_salary`, `employer_match.match_pct`,
`employer_match.cap_pct_of_pay`, `starting_contribution_pct` and `note`. It is loaded once and
validated: positive salary, percentages from 0 to 100, and a starting rate within the configured
range. See research R14.

## In-process types (not stored)

- **`Proposal`**: `action_type` and parsed `params`.
- **`GateResult`**: `step`, `reason`, `reply_text`, `pending_action_id`. Returned by the gate;
  `reply_text` becomes the assistant message (FR-013).
- **`ContributionSummary`**: the current and new rate, before and after amounts and differences
  for contribution and match, and `missed_match` (null when the new rate is at or above the cap).
  All amounts are `Decimal` values rounded to cents.
- **`ConfirmationToken`**: the raw token (never stored), the `pending_action_id`, `user_id` and
  `session_id`.
