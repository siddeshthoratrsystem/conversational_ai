# Contract: Front end ↔ back end changes (spec 011, revision 3)

**Change type**: one additive enum value. No new endpoints, request fields or status codes.

## `POST /api/chat`: unchanged shape

The request and response bodies are unchanged. When the agent's gate wrote the reply, `reply` holds
the gate's message and `message_id` is that message's ID. The back end only stores and returns it.
Gate refusals are ordinary `200` replies. Existing errors are unchanged (`400`, `401`, `403` for no
AI-planning access, `404`).

One internal change, invisible in the response: the back end creates the chat's `sessions` row
before calling the agent, instead of after. If the agent call or the message write then fails, the
session row stays without messages. It doesn't appear in `GET /api/sessions` (which joins messages),
and its history is empty.

## `GET /api/chat/{session_id}/history`: `source` widened

```json
"source": "agent | mock | gate | null"
```

`gate` marks an assistant message written by the action gate, as reported by the agent's `source`
field (contracts/agent-api.md). A turn-1 explanation of a rejected request is model text and has
`source` `agent`.

**Consumers**:
- `frontend/packages/core/src/api.ts`: the `source` type includes `"gate"` (done). No component reads `source`.
- `README.md`: the API contract section is updated.

## Gate message texts (defaults; written by the agent's gate; covered by agent tests)

Amounts are formatted as `$1,234.56`. Placeholders are in braces. The code appends the footer
`Demo data: no real account was changed.` as the last line of every message in the first table,
after a blank line. The second table holds the sentences the tool returns to the model, so the
model can explain a rejection; they never get the footer.

**Replies written by the gate** (`source: gate`):

| Situation | Message |
|---|---|
| Staged | "Here's the change you asked for. Nothing has changed yet.\n- 401(k) contribution: {cur}% → {new}%\n- Your contribution: {c0} → {c1} a month ({±dc})\n- Employer match: {m0} → {m1} a month ({±dm})" + match line + "\n\nReply **confirm** within {n} minutes to make this change, or **cancel** to keep {cur}%." |
| Match unchanged | The employer-match line reads "- Employer match: {m0} a month (no change)" |
| Below the cap | Adds "\nHeads-up: at {new}% you would miss {missed} a month of employer match. The match is {match}% of what you contribute, up to {cap}% of pay." |
| Replaced | The staged message for the new request, preceded by "I've replaced your earlier pending change." |
| Try again (too slow or the write failed) | "I couldn't set up that change in time, so nothing has changed. Please ask again." |
| Executed | "Done. Your 401(k) contribution is now {new}% (it was {cur}%)." |
| Cancelled | "Cancelled. Your 401(k) contribution stays at {cur}%." |
| Expired | "That change expired after {n} minutes, so nothing was changed. Ask again if you still want it." |
| Not an exact reply (`not_exact_reply`) | "Reply exactly confirm or cancel." |
| Pending in another chat (`other_session`) | "That change can only be confirmed in the chat where it was proposed." |
| Nothing pending (`nothing_pending`) | "There is no change waiting for confirmation." |
| Token missing, expired or invalid, for a confirm or cancel message (logged, not audited) | "Your sign-in has expired. Please sign in again, then reply confirm or cancel." |
| Actions disabled by missing settings, or the store unreadable, for a confirm or cancel message (logged, not audited) | "Contribution changes aren't available right now." |
| Education only or not entitled (turn 2) | "I can't make changes to your account right now. I can still answer general questions." |
| Already handled | "That change has already been handled." |
| Step-up refused | "This change needs an extra sign-in check, which isn't available yet, so nothing was changed." |
| Stale | "Your contribution changed since this was proposed, so nothing was changed. Ask again to see the new figures." |
| Confirm failed (apply failed, database timeout) | "That change didn't go through, so nothing was changed. Please try again." |
| Unavailable (seed missing at confirm, unknown policy) | "Contribution changes aren't available right now." |

**Sentences returned to the model** (`status: "rejected"`, field `message`):

| Reason | Message |
|---|---|
| `out_of_range` | "The contribution rate must be between {min}% and {max}%." |
| `not_whole_pct` | "The contribution rate must be a whole percentage, for example 8%." |
| `same_as_current` | "Your contribution is already {cur}%." |
| `invalid_params` | "That change request couldn't be read." |
| `education_only`, `no_verified_participant`, `actions_unavailable` | "Changes to the account can't be made right now." |
| `seed_unavailable`, `unknown_action` | "Contribution changes aren't available right now." |
