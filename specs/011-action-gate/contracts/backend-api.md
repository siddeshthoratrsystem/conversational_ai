# Contract: Front end ↔ back end changes (spec 011)

**Change type**: one additive enum value. No new endpoints, request fields or status codes.

## `POST /api/chat`: unchanged shape

The request and response bodies are unchanged. When the gate handles a turn, `reply` holds the
gate's message (staged summary, result or refusal) and `message_id` is the gate message's ID. The
gate's refusals are ordinary `200` replies, not HTTP errors. Existing errors are unchanged
(`400`, `401`, `403` for no AI-planning access, `404`).

## `GET /api/chat/{session_id}/history`: `source` widened

```json
"source": "agent | mock | gate | null"
```

`gate` marks an assistant message whose text came from the action gate (research R9).

**Consumers**:
- `frontend/packages/core/src/api.ts`: the `source` type gains `"gate"`. No component reads `source`, so nothing renders differently.
- `README.md`: the API contract section is updated.

## Gate message texts (defaults; covered by tests)

Amounts are formatted as `$1,234.56`. Placeholders are in braces.

| Situation | Message |
|---|---|
| Staged | "Here's the change you asked for. Nothing has changed yet.\n- 401(k) contribution: {cur}% → {new}%\n- Your contribution: {c0} → {c1} a month ({±dc})\n- Employer match: {m0} → {m1} a month ({±dm})" + match line + "\nReply **confirm** within {n} minutes to make this change, or **cancel** to keep {cur}%. (Demo data only.)" |
| Match unchanged | The employer-match line reads "- Employer match: {m0} a month (no change)" |
| Below the cap | Adds "\nHeads-up: at {new}% you would miss {missed} a month of employer match. The match is {match}% of what you contribute, up to {cap}% of pay." |
| Executed | "Done. Your 401(k) contribution is now {new}% (it was {cur}%). This changed demo data only." |
| Cancelled | "Cancelled. Your 401(k) contribution stays at {cur}%." |
| Replaced | The staged message for the new proposal, preceded by "I've replaced your earlier pending change." |
| Expired | "That change expired after {n} minutes, so nothing was changed. Ask again if you still want it." |
| Out of range | "The contribution rate must be between {min}% and {max}%." |
| Not whole | "The contribution rate must be a whole percentage, for example 8%." |
| Same as current | "Your contribution is already {cur}%." |
| Education only | "I can't make changes to your account right now. I can still answer general questions." |
| Nothing pending | "There's no pending change to confirm." / "…to cancel." |
| Other chat | "That change can only be confirmed or cancelled in the chat where you asked for it." |
| Not exact reply | "To make the pending change, reply exactly **confirm**; to keep things as they are, reply **cancel**. To ask for a different rate, just tell me the new rate." |
| Already handled | "That change has already been handled." |
| Step-up refused | "This change needs an extra sign-in check, which isn't available yet, so nothing was changed." |
| Stale | "Your contribution changed since this was proposed, so nothing was changed. Ask again to see the new figures." |
| Unavailable | "Contribution changes aren't available right now." (seed missing, unknown action, apply failed) |
