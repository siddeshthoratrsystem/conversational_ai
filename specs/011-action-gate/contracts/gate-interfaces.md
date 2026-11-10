# Contract: Gate interfaces (spec 011, internal to the back end)

These are the seams that must hold as the POC grows: new action types, a real contribution source
and step-up authentication (method still to be decided). They are Python protocols in
`backend/app/actions/`. The signatures below are the contract; the bodies are not.

## `ActionType` (one per kind of action; FR-002)

```python
class ActionType(Protocol):
    name: str                                    # "contribution_change"

    def parse(self, params: dict) -> dict: ...   # raises GateRefusal("invalid_params") on bad or unknown keys
    def check(self, participant_id: str, params: dict) -> dict: ...
        # raises GateRefusal(<reason code>) or returns the snapshot used for the summary
    def summary(self, params: dict, snapshot: dict, expiry_minutes: int) -> str: ...
    def execute(self, participant_id: str, params: dict, snapshot: dict,
                token: ConfirmationToken) -> str: ...
        # runs the change through its service; returns the result message
```

Registry: `ACTION_TYPES: dict[str, ActionType]`. Adding account opening, funding or transfers
means adding an entry. The gate flow does not change.

## `ContributionService` (the only way the gate reads or changes contributions; FR-021)

```python
class ContributionService(Protocol):
    def current_rate(self, participant_id: str) -> int: ...
    def apply_change(self, participant_id: str, new_rate_pct: int,
                     token: ConfirmationToken) -> int: ...  # returns the new rate
```

- `DemoContributionService(db, seed, redeem)`: `current_rate` reads `contributions`, falling back
  to the seed. `apply_change` calls `redeem(token)` first (single use; research R5), then upserts
  `contributions`.
- A future `PrincipalContributionService` keeps the same two methods. It redeems the token the
  same way and sends `token.pending_action_id` as the idempotency key. The gate does not change.
- Provided by the FastAPI dependency `get_contribution_service`, so tests and later deployments can swap it.

## `StepUpCheck` (hook for step-up authentication; FR-012)

```python
class StepUpCheck(Protocol):
    def verify(self, participant_id: str, action_type: str, claims: dict) -> bool: ...
```

- Order at confirm: mark `confirmed`, issue the token, `verify`, then `execute` (which redeems the
  token and writes the change). If `verify` returns false, the transaction rolls
  back, the change stays pending, and a `rejected` (`step_up_required`) entry is written.
- `AlwaysPass` is the default, provided by the FastAPI dependency `get_step_up_check`.

## `ActionGate` (the flow; called only from `POST /api/chat`)

```python
class ActionGate:
    def classify_reply(self, db, participant_id, session_id, message) -> ReplyKind | None: ...
        # read-only, before the agent call: CONFIRM, CANCEL or NOT_EXACT, or None (send to the agent)
    def handle_reply(self, db, participant_id, session_id, kind, education_only, claims) -> GateResult: ...
    def handle_proposal(self, db, participant_id, session_id, action: dict, education_only) -> GateResult: ...
```

- The `handle_*` methods run inside `_persist`'s transaction (research R6). They write state and
  audit rows and never commit themselves.
- Both refuse with `no_participant` when `participant_id` is empty (FR-016), and with
  `education_only` when the flag is set (FR-011).
- Both first expire this participant's overdue pending changes (research R7).
- After commit, `chat()` calls `emit_gate_outcome(...)` once for each gate decision.

## GR-ACTION-GATE trace event (optional; independent of PR #11)

When the current OpenTelemetry span is recording, the gate adds an event named `guardrail.check`
with these attributes:

| Attribute | Values |
|---|---|
| `guardrail_rule_id` | `GR-ACTION-GATE` |
| `guardrail_result` | `pass` for staged, confirmed, cancelled or executed; `fail` for rejected, expired or failed |
| `guardrail_reason` | Reason code from data-model.md |
| `guardrail_action` | `allow` or `block` |
| `action.type` | for example `contribution_change` |
| `action.step` | audit step |

- No participant ID, rates or chat text.
- If `opentelemetry` is not installed, no tracer is configured, or recording raises, the event is
  skipped silently. The gate outcome and the audit row are never affected.
- This matches the `guardrail.check` event in PR #11's `trace-schema.md` v1.1.0. The new rule ID and
  the `block` action value are additive to that contract.
