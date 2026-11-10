# Contract: Back end ↔ agent, `action` field (spec 011)

**Change type**: additive, optional (constitution I). The request is unchanged.

## Request (unchanged)

```json
{ "prompt": "string", "session_id": "string", "education_only": true }
```

`education_only` is still sent only when true. No participant ID is sent (research R2).

## Response

```json
{ "reply": "string", "intent": "string | null",
  "action": { "type": "contribution_change", "params": { "new_rate_pct": 8 } } }
```

- `action` is optional. It is left out (or `null`) when the model didn't call an action tool in this turn.
- `action.type` is a string naming a registered action type. Today the only one is `contribution_change`.
- `action.params` is an object. For `contribution_change` the only key is `new_rate_pct`, a number.
- The agent sends at most one `action` per turn: the last tool call in the turn.
- The agent never sends confirmations, tokens or participant IDs.

## Back-end handling

| `action` received | Back-end behaviour |
|---|---|
| absent or `null` | As today: `reply` is used, `source = 'agent'` |
| a valid object | The gate decides (propose flow). The gate's message replaces `reply`, `source = 'gate'` and `latency_ms` is kept |
| malformed (not an object, `type` not a string, `params` not an object) | Logged as a warning and treated as absent. `reply` is still used. It is not a fallback to mock, because `reply` is valid |
| unknown `type` or bad `params` | Handled by the gate: `proposed` then `rejected` (`unknown_action` or `invalid_params`), and a plain message |

The mock fallback (no `AGENT_URL`, timeout, non-2xx, bad body) never has an `action`, so nothing
is proposed when the agent is unavailable.

## Agent tool

`request_contribution_change(new_rate_pct: float | str)`, in `agent/src/wealth_agent/action_tools.py`:

- Returns `{ok: false, error}` when `new_rate_pct` is missing or not a finite number. This is the
  same `_safe` and `_number` style as `tools.py`, which it imports without changing.
- Otherwise it records the action on `tool_context.agent.state` under `pending_action_request`
  and returns:
  `{ok: true, status: "sent_for_confirmation", note: "The system will show the participant what changes and ask them to reply confirm or cancel. Do not say the change has been made."}`
- It applies no range or business rules; the gate is the only authority for those.
