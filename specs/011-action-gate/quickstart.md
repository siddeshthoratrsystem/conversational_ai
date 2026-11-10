# Quickstart: Action Gate (spec 011)

How to check the feature works. Contracts: [contracts/](./contracts/). Tables and reason codes:
[data-model.md](./data-model.md).

## 1. Automated tests (no Postgres, Ollama or network)

```bash
cd backend && source .venv/bin/activate && pytest          # existing suite + gate tests
cd ../agent && source .venv/bin/activate && pytest          # existing suite + action tool tests
cd ../frontend && npm test                                   # unchanged behaviour; source type widened
```

Expected: all pass. Each rule in spec 011 maps to at least one test (tasks.md will list them).
The five cases named in the spec's success criteria:

| Case | Where | What it checks |
|---|---|---|
| "Skip confirmation" | `backend/tests/test_action_gate.py` | A fake agent returns an `action` and a reply saying "done". The reply is replaced by the staged summary, and the rate is unchanged |
| Expired confirmation | same | Stage at t0, confirm at t0 + 301 s with an injected clock. The audit shows `expired`, and the rate is unchanged |
| Reused token | `backend/tests/test_contribution.py` | `apply_change` with a redeemed token is refused (`already_handled`), and the rate changes once |
| Different participant confirms | `test_action_gate.py` | Bob's "confirm" gives `nothing_pending`, and Alice's change stays pending. Alice's token used for Bob gives `token_invalid` |
| Decrease below the match | `test_contribution.py`, `test_action_gate.py` | 5%→3% summary shows −$166.67 and warns of $166.67 missed match. Confirm runs the change |

Migration check against real Postgres (needs Docker):

```bash
docker compose up --build    # start.sh runs `alembic upgrade head`, now including 0005
```

## 2. Manual end-to-end demo (needs Ollama and the agent server)

```bash
ollama serve                                               # llama3.2
cd agent && uv run agent.py                                # :8080
AGENT_URL=http://host.docker.internal:8080/invocations docker compose up --build
cd frontend && npm run web                                 # http://localhost:5173, sign in as alice
```

Or call the API by hand. Get `$TOKEN` as in README "Backend: sign-in check and the local stand-in", then:

```bash
say() { curl -s -X POST http://localhost:8000/api/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "{\"session_id\":\"gate-1\",\"message\":\"$1\"}"; echo; }
say "change my 401(k) contribution to 8%"   # summary: 5% → 8%, +$250.00 a month, match no change
say "confirm"                               # "Done. Your 401(k) contribution is now 8% ..."
say "change my 401(k) contribution to 3%"   # summary with the missed-match heads-up
say "cancel"                                # "Cancelled. ... stays at 8%."
say "confirm"                               # "There's no pending change to confirm."
```

Then check:
- **Same chat only**: propose in `gate-1` and send "confirm" with `session_id` `gate-2`. Expect "only … in the chat where you asked for it".
- **Expiry**: start the back end with `ACTION_EXPIRY_SECONDS=10`, propose, wait 11 s, confirm. Expect the expired message.
- **Education only**: start with `ENTITLEMENT_MODE=unavailable` and propose. Expect "I can't make changes … right now"; ordinary questions are answered as before.
- **Agent down**: stop the agent and propose. You get the mock reply and nothing is staged. Confirm and cancel still answer, because they don't need the agent.
- **Survives restart**: propose, restart the back-end container, confirm within 5 minutes. The change runs.
- **Audit record**:

  ```bash
  docker compose exec db psql -U app convai -c \
    "select user_id, action_type, pending_action_id, step, reason, created_at from action_audit order by id"
  ```

  Expect one row per step, with only these columns.

The CLI (`python -m wealth_agent`) shows only the model's side: it calls the tool and says you
will be asked to confirm. The gate itself runs in the back end.

## 3. Tracing (optional; does not need PR #11)

GR-ACTION-GATE events appear only when the back end has an OpenTelemetry tracer. PR #11 adds one
to the agent process only. To see the event before back-end tracing exists, run the back end
under `opentelemetry-instrument` with a console exporter. This is a manual check; the automated
test uses a fake span.
