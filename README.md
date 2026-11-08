# Conversational AI — POC

Chat app (ChatGPT-like) → FastAPI backend → AWS Bedrock AgentCore agent that captures customer intent.

| Folder      | What                              | Owner  |
|-------------|-----------------------------------|--------|
| `frontend/` | Website and mobile app, with shared packages | Vinod  |
| `backend/`  | FastAPI + Postgres                | Rajesh |
| `agent/`    | AgentCore agent (needs R Systems AWS + AgentCore access) | TBD |

## API contract (FE ↔ BE)

**Sign-in (spec 008).** Every endpoint except `GET /api/health` needs `Authorization: Bearer <access token>` from the
identity provider. The user is the token's `sub`; nothing else can set it. Request and response bodies are unchanged.
Added responses, all `{"detail": "<message>"}`:

- `401 "missing or invalid bearer token"` (with `WWW-Authenticate`) for a missing, malformed, unsigned, badly signed,
  expired (more than 60 s ago), wrong-issuer, wrong-audience or no-`sub` token. It never says which check failed.
- `404` for another user's chat or message, and for a chat created before sign-in existed, with the same response as
  one that doesn't exist (`"session not found"` for chat and history, `"message not found"` for feedback).
- `503 "sign-in service unavailable, try again later"` when the identity provider's keys can't be fetched at all.

See `specs/008-oidc-auth/contracts/` for the details.

**Access to AI planning (spec 009).** A stand-in check until the business supplies real rules: the token's boolean
`ai_planning` claim decides, `ENTITLEMENT_DENY` (user ids or usernames) always refuses, and a missing claim fails
closed to education only (`ENTITLEMENT_MODE=unavailable` forces that for everyone). A refused chat returns
`403 "AI planning is not available for this account"` and stores nothing. See `specs/009-sign-in-session-access/`.

`GET /api/me`: who is signed in and what they may use.
```json
{ "user_id": "token sub", "name": "token name, else preferred_username, else sub", "access": "granted | denied | unavailable" }
```

`POST /api/chat`
```json
// request
{ "session_id": "string", "message": "string" }
// response
{ "session_id": "string", "reply": "string", "intent": "string | null", "message_id": "integer | null" }
```
In education-only mode the response also has `"education_only": true`; otherwise the field is left out.
`message_id` is the id of the assistant message created for this reply, and it is the id to rate with the feedback
endpoint below. It is always an integer today. Clients that don't use it can ignore it.

`POST /api/messages/{message_id}/feedback`: rate one assistant message. Submitting again for the same message replaces
the earlier feedback.
```json
// request: rating is required; reason (only with "down") and comment (max 1000 chars) are optional
{ "rating": "up | down", "reason": "incorrect | unclear | wanted_a_person | other", "comment": "string" }
// response 200 (created or replaced)
{ "message_id": 42, "rating": "down", "reason": "string | null", "comment": "string | null",
  "trace_id": null, "created_at": "ISO-8601", "updated_at": "ISO-8601" }
```
`trace_id` is always `null` until agent tracing exists, and the reason list is provisional (pending approval).
Invalid input returns 400 `{"detail": "<message>"}` and stores nothing: a `message_id` that isn't a positive whole
number, a body that isn't a JSON object, a bad `rating`, `reason` or `comment`, `reason` with `"up"`, or a user
message (only assistant messages can be rated). An unknown message returns 404 `{"detail": "message not found"}`.
See `specs/002-answer-feedback/contracts/feedback-api.md` for the exact messages.

`GET /api/chat/{session_id}/history`: every message in the caller's session, oldest first. An unknown session, or one that
belongs to someone else, returns 404 `{"detail": "session not found"}` (it used to return `"messages": []`).
```json
{ "session_id": "string",
  "messages": [ { "id": 1, "role": "user | assistant", "content": "string",
                  "intent": "string | null", "latency_ms": "number | null",
                  "source": "agent | mock | null", "created_at": "ISO-8601" } ] }
```

`GET /api/sessions?ids=<id>&ids=<id>…`: summaries of the given sessions for the sidebar, most recently active first.
The frontend sends the session IDs this browser has used. Unknown IDs, and IDs of other users' sessions, are skipped, and more than 200 IDs returns
400 `{"detail": "too many session ids (max 200)"}`.
```json
{ "sessions": [ { "session_id": "string", "title": "first user message (max 80 chars + …)",
                  "created_at": "ISO-8601", "last_active_at": "ISO-8601" } ] }
```

`GET /api/health` → `{ "status": "ok" }`

The backend calls the agent with `{ "prompt": "<message>", "session_id": "..." }` (plus `"education_only": true` in
education-only mode) and expects `{ "reply": "...", "intent": "..." }` back. Until AgentCore access is ready, the backend returns a mock reply.

## Run locally

```bash
# Postgres + backend + local sign-in service (Keycloak)
docker compose up --build        # backend on http://localhost:8000, Keycloak on http://localhost:8081

# Frontend
cd frontend && npm install && npm run web   # http://localhost:5173 (proxies /api to :8000)

# Agent (once AWS access is set up)
cd agent && uv run agent.py      # local AgentCore runtime on http://localhost:8080
```

## Sign-in (specs 008 and 009)

The backend needs three settings (see `.env.example`) and won't start without them: `OIDC_ISSUER` (the token's `iss`),
`OIDC_AUDIENCE` (the `aud` it accepts) and `OIDC_JWKS_URL` (where the provider publishes its public keys). The web
app signs customers in with OpenID Connect (authorization code with PKCE); the token stays in memory and is renewed
silently. Locally, a Keycloak container (realm `convai`, imported from `infra/keycloak/`) stands in for the client's
Okta, and `docker compose` points the backend at it. Moving to Okta changes settings only. Full checks:
`specs/009-sign-in-session-access/quickstart.md`.

Test users in the local realm only (password = username + `-test`): `alice` (has access), `bob` (no access to AI
planning), `carol` (has access; sets up a one-time code on first sign-in). Keycloak admin: http://localhost:8081
(`admin` / `admin`).

Get a token and call the API by hand (the `convai-dev-cli` client exists only in the local realm):

```bash
TOKEN=$(curl -s http://localhost:8081/realms/convai/protocol/openid-connect/token \
  -d grant_type=password -d client_id=convai-dev-cli -d username=alice -d password=alice-test \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST http://localhost:8000/api/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"session_id":"demo-1","message":"hi"}'
```

| Setting | Where | Default | Meaning |
|---|---|---|---|
| `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` | backend | none (compose: local Keycloak) | Required; the token check |
| `ENTITLEMENT_MODE` | backend | `claim` | Access from the token's `ai_planning` claim; `unavailable` forces education only |
| `ENTITLEMENT_DENY` | backend | empty | Comma-separated user ids or usernames always denied |
| `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID` | web | local realm, `convai-web` | Change these two for Okta |
| `VITE_IDLE_TIMEOUT_MINUTES`, `VITE_IDLE_WARNING_MINUTES` | web | `15`, `2` | Idle sign-out and the warning before it |

To use Okta: set `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID` and the three `OIDC_*` settings, and register these
redirect URIs in Okta: `<origin>/auth/callback`, `<origin>/silent-callback.html` and `<origin>/`. The "next step" text
for customers without access ("Contact Principal support for help.") is a placeholder until the business words it.

Tests make their own keys and tokens and need no identity provider. `backend/devtools/stand_in_idp.py` (spec 008, any
username, password grant) still works for quick tokens if you point the three `OIDC_*` settings at it. On an
Intel-Mac Python, `requirements-dev.txt` installs a prebuilt `cryptography` wheel, because newer versions only publish
arm64 wheels for macOS.

## Backend: run and test

```bash
# Run (Postgres + backend; migrations run on startup)
docker compose up --build

# Test (no Postgres needed; uses in-memory SQLite)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Agent: local wealth agent (Strands + Ollama)

Spec: `specs/005-wealth-agent/`. Runs fully locally against Ollama (`llama3.2` by default); synthetic data, read-only tools.

```bash
ollama pull llama3.2 && ollama serve          # http://localhost:11434
cd agent
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                        # unit tests, no Ollama needed
PYTHONPATH=src python -m wealth_agent         # interactive chat
PYTHONPATH=src python evals/run_eval.py       # live golden-case eval (needs Ollama)
```

Config: `WEALTH_AGENT_PROVIDER` (only `ollama`), `OLLAMA_HOST`, `OLLAMA_MODEL`.

## Frontend: structure

`frontend/` is one npm workspace, so run `npm install` once in `frontend/`. If you have an older checkout, delete
`frontend/node_modules` first. Apps run things and packages share things: apps can import packages, and packages never
import apps.

| Folder | What lives there |
|--------|------------------|
| `apps/web/` | The website (Vite): chat screens (`src/chat/`), sign-in (`src/auth/`), browser services, tests |
| `apps/mobile/` | The mobile app (Expo, React Native): starter screen for now |
| `packages/ui/` | Shared components. `src/button/` has web and native files; `src/web/` holds web-only components |
| `packages/core/` | API client and types, text parsing and server time parsing. No UI or platform code |
| `packages/tokens/` | Figma design tokens in `tokens.json`, and the CSS generated from them |

Commands, from `frontend/`:

| Command | What it does |
|---------|--------------|
| `npm run web` | Starts the website |
| `npm run mobile` | Starts the Expo dev server (needs a simulator, or Expo Go on a device) |
| `npm test` | Runs all tests. Fetch is mocked, and no backend or simulator is needed |
| `npm run build` | Type checks and builds the website, and type checks the mobile app |
| `npm run bundle:mobile` | Checks that the mobile app bundles for iOS and Android |
| `npm run tokens` | Regenerates the theme CSS after a change to `tokens.json` |

The mobile app must call `configureApi({ baseUrl })` from `@convai/core` before using the API, because a native app has
no page origin. The website keeps the relative `/api` path.

## Frontend: UI kit and theme

The UI follows the Figma file *WPI Day 1.5 (P&A and P&E)*, by way of the Alfred mock UI built from it.
The chat is the full-page Alfred layout (Figma frame A9): header, left icon rail, a History panel for past chats,
and the "Good morning" welcome (frame S1) on an empty chat.

- **Design tokens** (colors, type scale, radii, shadows, gradients) live only in
  `frontend/packages/tokens/tokens.json`. `npm run tokens` turns them into a Tailwind v4 theme for the website
  (Tailwind's default colors removed, so classes like `bg-primary`, `text-navy` and `shadow-card` always match the
  design) and Uniwind colors for the mobile app. No hex colors anywhere else; a test enforces this. Light only.
- **Font:** the design uses FS Elliot Pro (licensed). The website falls back to Source Sans 3 (`@fontsource`).
- **Components** live in `frontend/packages/ui/` and are plain React + Tailwind, with unstyled
  [Radix UI](https://www.radix-ui.com) primitives where behavior matters (tabs, toggle groups). Import them as
  `@convai/ui/<name>`, for example `@convai/ui/card`:

  | Component | Use |
  |---|---|
  | `button` | `primary`, `secondary`, `link`, `ai` (gradient), `ghost`; sizes `sm`, `md`, `lg`, `icon`. Web and native |
  | `ai-button` | Alfred's full-width gradient call to action (welcome cards) |
  | `chip`, `choice-chips` | Alfred quick replies; pick-one chip group (a radio group for screen readers) |
  | `text-field`, `textarea` | Labelled inputs with error state |
  | `card`, `status-tag`, `progress-bar`, `key-value-list`, `tabs` | Dashboard building blocks for the next screens |
  | `logo`, `soundwave` | Brand assets from Figma (`src/assets/brand/`) and the composer's voice glyph |
  | `cn` | Joins class names; later Tailwind classes win |

- Add a component as `packages/ui/src/web/<name>.tsx`, using only token classes. Web-only components fail at type
  check and bundling if imported in the mobile app. To port one, move it to `packages/ui/src/<name>/` with shared
  types and web and native files, and add it to `exports` in `packages/ui/package.json`. See
  `specs/007-shared-ui-library/contracts/`. On native, `ai` is a solid blue until gradients are supported.
- **Sign-in** (spec 009): `src/auth/` runs the OIDC sign-in, renews the token, signs out after 15 idle minutes (with a
  warning) and brings the customer back to the same chat and unsent text. `ChatApp` shows the access notices.
- Answer feedback: thumbs up/down, an optional reason and a comment under each reply, sent to
  `POST /api/messages/{message_id}/feedback` (spec 002). Ratings are shown for the current visit only;
  history does not return them yet. See `specs/004-answer-feedback-ui/`.

## Feature development (Spec Kit)

New features use [Spec Kit](https://github.com/github/spec-kit), in Claude Code, from the repo root.
Project rules live in `.specify/memory/constitution.md`, and each feature's artifacts are written to `specs/<feature>/`.

1. `/speckit-specify <what you want and why>`: writes the feature spec to `specs/<feature>/spec.md`. Create your feature branch first.
2. `/speckit-clarify` (optional): answers open questions in the spec.
3. `/speckit-plan <tech notes>`: produces the implementation plan and checks it against the constitution.
4. `/speckit-tasks`: breaks the plan into ordered tasks. Run `/speckit-analyze` (optional) to check consistency.
5. `/speckit-implement`: builds the feature from the tasks.

Review the generated spec and plan before moving to the next step.

### End to end with `/pdlc`

`/pdlc` runs the whole flow from a requirement to a pull request. It reads the requirement from Confluence or Jira, then
writes the spec, gets the Figma design (or proposes one), plans, creates Jira tickets, builds with tests first, verifies
and opens the PR. It stops for your approval at the spec, design, plan, Jira and PR steps.

```text
/pdlc https://<org>.atlassian.net/wiki/spaces/…/pages/…    # from a Confluence page
/pdlc CONVAI-123                                            # from an existing Jira ticket
/pdlc CONVAI-123 https://www.figma.com/design/…             # with a Figma link
/pdlc resume                                                # continue the run on this branch
```

- Steps: `.pdlc/PLAYBOOK.md`. Settings (Jira project, issue types, statuses, custom fields, Figma, branches, verify
  commands, gates): `.pdlc/config.yaml`. No secrets: Confluence, Jira and Figma sign in through their MCP servers.
- Works in Claude Code (`/pdlc`), Cursor (`/pdlc`, MCP servers in `.cursor/mcp.json`) and GitHub Copilot in VS Code
  (`/pdlc` prompt, MCP servers in `.vscode/mcp.json`).
- In Claude Code, a hook (`.pdlc/hooks/guard.py`) blocks pushes to `main` and blocks opening a PR before verify passes.
  Test it with `python3 -m unittest discover -s .pdlc/hooks`.
- Opening the PR uses the GitHub CLI: `brew install gh && gh auth login`. If an API contract changes, update the contract section above in the same PR.
