# Contract: Back end ↔ agent (spec 011, revision 3)

**Change type**: additive (constitution I). The request body is unchanged. The request gains a
header, the response gains one optional field, and the back end's timeout becomes a setting.
Revision 1's `action` response field is dropped; it was never merged.

## Request

```http
POST {AGENT_URL}
Authorization: Bearer <the participant's own access token, as received by the back end>
Content-Type: application/json

{ "prompt": "string", "session_id": "string", "education_only": true }
```

- `Authorization` is new. The back end sends the participant's token unchanged, only after its own
  sign-in check has accepted it (`auth.verified_token`), and never logs it.
- Before the call, the back end has created and committed the `sessions` row for `session_id`
  (owned by this participant). The agent relies on it for the `pending_actions.session_id` foreign key.
- The body is unchanged. `education_only` is still sent only when true. No participant ID is sent;
  the agent uses the verified token's `sub`.
- The back end waits up to `AGENT_TIMEOUT_SECONDS` (default 60; was a fixed 10).
- Without a valid token, the agent answers normally with every action refused. It does not return 401.

## Response

```json
{ "reply": "string", "intent": "string | null", "source": "gate" }
```

- `source` is optional and new. It is `"gate"` when the action gate wrote the reply: a staged
  summary, a "try again", or a confirm, cancel, expired or refused reply. It is left out when the
  model wrote the reply, including the model's explanation of a rejected request. No other value
  is sent.
- The agent never returns confirmation tokens, participant IDs or gate state.

## Back-end handling

| Response | Back-end behaviour |
|---|---|
| `source` absent or `null` | Store with `source = 'agent'` |
| `source` is `"gate"` | Store with `source = 'gate'`; `latency_ms` recorded |
| `source` is any other value or type | Log a warning, store as `agent` (not a fallback; `reply` is valid) |
| Failure (no `AGENT_URL`, timeout, non-2xx, bad body) | Mock reply as today. If the agent committed a gate step anyway, its audit is the record (data-model.md) |

## Agent behaviour per message

For a message that is exactly, or starts with, an accepted confirm or cancel reply, plain code
replies with `source: "gate"` and the model is never called, even when actions can't run. The
first row that applies wins (spec FR-005, same order):

| # | Situation | Reply | Audit |
|---|---|---|---|
| 1 | Agent sign-in or database settings missing (actions disabled) | "Contribution changes aren't available right now." | none; logged and traced |
| 2 | Token missing, expired or invalid | "Your sign-in has expired. Please sign in again, then reply confirm or cancel." | none; logged and traced with the case: `sign_in_token_missing`, `sign_in_token_expired` or `sign_in_token_invalid` |
| 3 | Store can't be read (error or time-out) | "Contribution changes aren't available right now." | none; logged and traced (`store_failed`) |
| 4 | Exact reply, and an unexpired pending change exists for this participant in this chat | Confirm or cancel it (or refuse `education_only` if actions aren't allowed this turn) | as the step |
| 5 | Exact reply, and this chat's pending change expired on this message | The gate's expired message | `expired` |
| 6 | Extra words, and a change is pending in this chat | "Reply exactly confirm or cancel." | `rejected` (`not_exact_reply`) |
| 7 | Nothing pending in this chat, but pending in another chat of this participant | "That change can only be confirmed in the chat where it was proposed." | `rejected` (`other_session`) |
| 8 | Nothing pending | "There is no change waiting for confirmation." | `rejected` (`nothing_pending`) |

Every other message goes to the model:

| Outcome of the model turn | Reply |
|---|---|
| It called `request_contribution_change`, the check held, and the turn is under `ACTION_STAGE_DEADLINE_SECONDS` | The gate stages; its summary is the reply, `source: "gate"` |
| The check held, but the turn passed the deadline or the write failed | The gate's "try again" reply, `source: "gate"` |
| Anything else | The model's reply with the disclaimer, no `source` |

At the end of the turn, within `ACTION_STAGE_DEADLINE_SECONDS`, one transaction writes a `rejected`
row for each request the check rejected and then stages a held request. Past the deadline, or on a
failed write, nothing is recorded or staged.

A request without a verified token runs with a fresh, empty conversation that is not kept; two
token-less requests never share one, even with the same `session_id`.

Without a verified participant, or with actions disabled at start-up, a message that isn't a
confirm or cancel message goes to the model. The tool returns `rejected` (`no_verified_participant` or
`actions_unavailable`) and nothing is written.

## Agent tool

`request_contribution_change(new_rate_pct: float)` in `agent/src/wealth_agent/action_tools.py`:

| Result | When |
|---|---|
| `{ok: false, error}` | `new_rate_pct` missing or not a finite number. Text such as "8%" or "eight" is refused; the model converts wording to a number |
| `{ok: true, status: "held", note}` | The gate's policy check passed. The request is kept in the turn's memory only. `note`: "The system will show the participant a summary and ask them to reply confirm or cancel. Do not say the change has been made." |
| `{ok: true, status: "rejected", reason, message}` | The policy check failed. `reason` is a code from data-model.md; `message` is the plain sentence to explain. No pending change is written; the rejection is recorded at the end of the turn |

There is no confirm or cancel tool.
