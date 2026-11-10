# Quickstart: Action Gate (spec 011, revision 3)

How to check the feature works. Contracts: [contracts/](./contracts/). Tables, writers and reason
codes: [data-model.md](./data-model.md).

## 1. Automated tests (no Postgres, Ollama, identity provider or network)

```bash
cd agent && source .venv/bin/activate && pip install -r requirements-dev.txt && pytest   # gate, policy, identity, tool, run_turn
cd ../backend && source .venv/bin/activate && pytest     # pass-through, schema owner, drift guard
cd ../frontend && npm test                                # unchanged behaviour; source type includes gate
```

Expected: all pass. The cases the decisions and the success criteria name:

| Case | Where | What it checks |
|---|---|---|
| "Skip confirmation" | `agent/tests/test_action_gate.py` | The scripted model calls the tool and writes "done". The reply is the staged summary with `source: gate`, and the rate is unchanged |
| Slow model past the deadline | same | Scripted model sleeps past `ACTION_STAGE_DEADLINE_SECONDS` (injected clock). "Try again" reply, nothing in `pending_actions` or `action_audit` |
| Failed or timed-out DB write | same | Store switch raises a database error, then a statement-timeout error. "Try again" reply, nothing staged |
| Rejected request | `test_action_tools.py`, `test_action_gate.py` | 51%: the tool returns `rejected` with `out_of_range` and the sentence; the model's reply explains it; one `rejected` audit row, no pending change |
| Confirm from another participant, another chat, after expiry, or with extra text | `test_action_gate.py` | Nothing runs and the model isn't called. Another participant: "There is no change waiting for confirmation." Another chat: "That change can only be confirmed in the chat where it was proposed." Extra text: "Reply exactly confirm or cancel." Each writes a `rejected` row. After expiry: the expired message and an `expired` entry |
| Turn memory per participant and chat | `test_action_gate.py` | Two participants' turns, interleaved and run at the same time, never see each other's turn context, held or rejected requests |
| Missing or invalid token | `test_action_gate.py`, `test_identity.py` | Actions refused (`no_verified_participant`), ordinary answer unchanged |
| Reused token | `agent/tests/test_contribution_service.py` | `apply_change` with a redeemed token is refused (`already_handled`), and the rate changes once |
| Decrease below the match | `test_contribution_policy.py`, `test_action_gate.py` | 5%→3% summary shows −$166.67 and warns of $166.67 missed match. Confirm runs the change |
| Turn 2 knows the outcome | `test_action_gate.py`; eval `contribution-now-after-confirm` | After "confirm", the conversation holds the gate's result without the footer |

Also covered:
- Missing OIDC or database settings, or deadline ≥ agent timeout: actions off, one warning (`test_action_config.py`).
- The token is forwarded and never logged; the session row exists before the agent is called; `source: gate` is stored (`backend/tests/test_chat.py`).
- The back end's timeout is `AGENT_TIMEOUT_SECONDS`, default 60 (`backend/tests/test_agent.py`).
- The agent's tables match the back end's models (`backend/tests/test_agent_store_schema.py`).

Migration check against real Postgres (needs Docker):

```bash
docker compose up --build    # start.sh runs `alembic upgrade head`, including 0005
```

## 2. Manual end-to-end demo (needs Ollama, Docker and the agent on the host)

```bash
ollama serve                                               # llama3.2
docker compose up --build -d db oidc backend               # Postgres :5432, stand-in IdP :8090, back end :8000
cd agent && DATABASE_URL=postgresql://app:app@localhost:5432/convai \
  OIDC_ISSUER=http://localhost:8090/default OIDC_AUDIENCE=convai-api \
  OIDC_JWKS_URL=http://localhost:8090/default/jwks uv run agent.py      # :8080; no start-up warning expected
AGENT_URL=http://host.docker.internal:8080/invocations docker compose up -d backend
cd frontend && npm run web                                 # http://localhost:5173, sign in as alice
```

Or call the API by hand. Get `$TOKEN` as in README "Backend: sign-in check and the local stand-in", then:

```bash
say() { curl -s -X POST http://localhost:8000/api/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "{\"session_id\":\"gate-1\",\"message\":\"$1\"}"; echo; }
say "change my 401(k) contribution to 8%"   # gate summary: 5% → 8%, +$250.00 a month, match no change
say "confirm"                               # "Done. Your 401(k) contribution is now 8% ..."
say "what's my contribution now?"           # the model says 8%, not "pending"
say "change my 401(k) contribution to 60%"  # the model explains the 0–50% range; recorded as rejected
say "change my 401(k) contribution to 3%"   # summary with the missed-match heads-up
say "cancel"                                # "Cancelled. ... stays at 8%."
say "confirm"                               # "There is no change waiting for confirmation."
```

Then check:
- **Same chat only**: propose in `gate-1` and send "confirm" with `session_id` `gate-2`. Expect "That change can only be confirmed in the chat where it was proposed."; the change is still pending in `gate-1`.
- **Exact reply only**: with a change pending, send "confirm please". Expect "Reply exactly confirm or cancel." and nothing runs.
- **Expiry**: start the agent with `ACTION_EXPIRY_SECONDS=10`, propose, wait 11 s, confirm. Expect the expired message.
- **Education only**: start the back end with `ENTITLEMENT_MODE=unavailable` and propose. Expect "can't be made right now" explained by the model; ordinary questions are answered as before.
- **Agent verifies the token itself**: call the agent directly without `Authorization` (`curl -s localhost:8080/invocations -d '{"prompt":"change my contribution to 8%","session_id":"x"}'`). Expect a refusal and nothing in `pending_actions`. "What is diversification?" is answered normally. Send `{"prompt":"confirm",...}` the same way: expect "Your sign-in has expired. Please sign in again, then reply confirm or cancel." and a log line naming `sign_in_token_missing`.
- **Agent misconfigured**: start the agent without `OIDC_*`, or with `ACTION_STAGE_DEADLINE_SECONDS=60`. Expect one warning naming the problem, chat working, and actions refused. "confirm" gets "Contribution changes aren't available right now." and no model call.
- **Agent down**: stop the agent and send "confirm". You get the mock reply; the pending change expires unless the agent is back and you confirm in time.
- **Survives restart**: propose, restart the agent, confirm within 5 minutes. The change runs.
- **Audit record**:

  ```bash
  docker compose exec db psql -U app convai -c \
    "select user_id, action_type, pending_action_id, step, reason, created_at from action_audit order by id"
  ```

  Expect, in order: `staged`, `confirmed`, `executed`; `rejected` (`out_of_range`, no
  `pending_action_id`) for 60%; `staged`, `cancelled`; and `rejected` (`nothing_pending`). Only
  these columns appear.

The CLI (`python -m wealth_agent`) calls the model directly, not `run_turn`, so the tool returns
`actions_unavailable` there.

## 3. Live evals (needs Ollama)

```bash
cd agent && PYTHONPATH=src python evals/run_eval.py
```

The contribution cases include `contribution-now-after-confirm`, which runs three turns through
`run_turn` with an in-memory store and a locally signed token.

## 4. Tracing (optional; does not need PR #11 merged)

Once PR #11 is merged, run the agent with `TRACING_MODE=console`. Each gate outcome, including the
unaudited `no_verified_participant`, `too_slow` and `store_failed`, adds a `guardrail.check` event with
`guardrail_rule_id = GR-ACTION-GATE`, either on the turn's span or on a `wealth_agent.action_gate`
span of its own. Before PR #11, the automated test with a fake span is the check.
