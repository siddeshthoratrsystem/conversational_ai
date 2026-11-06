# Implementation Plan: Customer Sign-In, Session Timeout and Access to AI Planning

**Branch**: `009-sign-in-session-access` | **Date**: 2026-11-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-sign-in-session-access/spec.md`

## Relationship to spec 008

Spec 008 (`specs/008-oidc-auth/`) gave the backend token check (`app/auth.py`, settings
`OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, all required, no "off" mode), per-user chats
(`sessions.user_id`, migration `0003`, 404 for someone else's chat) and the dev-only stand-in
(`backend/devtools/stand_in_idp.py`) with a demo password sign-in. Spec 009 adds real web
sign-in (code + PKCE, token in memory, silent renewal, sign-out at the provider), Keycloak as the
local Okta stand-in with an MFA test user, idle timeout with warning and resume (BL-055), and the
AI-planning access check with education-only fallback. Backlog: BL-001 (real sign-in screen,
MFA), BL-055, C.8.3.1-S1, OI-06.

## Summary

Replace spec 008's demo sign-in with OpenID Connect sign-in (authorization code + PKCE). Locally
a Keycloak container stands in for the client's Okta; switching is a settings change. The web app
keeps tokens in memory, renews them in the background, signs the customer out after an idle
period with a warning, and brings them back to the same chat and draft. The backend keeps spec
008's token check and ownership, and adds a stand-in entitlement check that fails closed to
education only. Decisions are in [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 7, React 19.3 (web)

**Primary Dependencies**: Backend: none new (`pyjwt[crypto]` came with spec 008). Web adds
`oidc-client-ts` 3.5 (OIDC sign-in, renewal, sign-out). Local identity provider: Keycloak 26.4
in Docker. Everything else is the existing stack.

**Storage**: PostgreSQL; migration `0004` adds `sessions.access` and `sessions.access_checked_at`
([data-model.md](./data-model.md)). Browser: tokens in memory, resume state in `sessionStorage`.

**Testing**: pytest with in-memory SQLite and spec 008's test keys and `make_token` (now with
`ai_planning: True` by default). Vitest + Testing Library + jsdom, with the sign-in library
replaced by a fake in tests; fake timers for the idle timeout.

**Target Platform**: Modern desktop and mobile browsers; backend on Linux/macOS

**Project Type**: Web application (frontend workspace + FastAPI backend)

**Performance Goals**: Returning customer reaches the message box in under 30 s including
sign-in (SC-001). The access check reads claims already verified; no extra call.

**Constraints**: Tokens never in `localStorage` (FR-003). Switching provider by settings only
(FR-002). Tests need no Keycloak, Postgres or network (Principle IV). No setting turns the token
check off (spec 008). The mobile app's `configureApi({ baseUrl })` keeps compiling.

**Scale/Scope**: Backend: one new module (entitlement), one migration, one new endpoint, changes to
`POST /api/chat`, a `verified_claims` dependency. Web: one auth module, a provider component, an
idle hook, the sign-in prompt and two notices; one Keycloak realm file.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Contract-First Interfaces | Pass | Contracts in [contracts/](./contracts/) before code. All changes are additive: `GET /api/me` is new, `education_only` is optional and left out unless true, the agent body gains `education_only` only when true. The new 403 applies only to accounts the check denies; stand-in and test tokens carry `ai_planning: true`, so existing callers keep working. Spec 008's 401/404/503 are unchanged. README updated; Rajesh reviews the backend PR, Vinod the web PR. |
| II. Graceful Agent Degradation | Pass | Agent fallback unchanged. Entitlement failure degrades to education only, never an error. The mock reply also reports `education_only`. |
| III. Persistence Through Alembic Only | Pass | Migration `0004`, forward-applicable, two nullable columns. The access fields are written in the same transaction as the turn's messages. A denied turn stores nothing. |
| IV. Tests Run Without External Services | Pass | Backend tests use spec 008's local keys; frontend tests replace the OIDC client. Every scenario and edge case gets a test. |
| V. POC Simplicity | Pass, one dependency and one service justified | `oidc-client-ts` and the Keycloak container are justified in Complexity Tracking. No users table, no backend-for-frontend, no runtime config file. |

Technology constraints: settings by environment variables, listed in the root `.env.example`
(backend) and `frontend/apps/web/.env.example` (web). Test user passwords are local test values in
the realm file, not secrets. Error bodies keep `{"detail": ...}`.

**Post-design re-check**: Pass.

## Delivery: two stacked pull requests

1. **Backend PR**, branch `009-sign-in-access-backend` (based on main): `app/auth.py`
   (`verified_claims`), `app/entitlement.py`, `app/main.py`, `app/agent.py`, `app/models.py`,
   migration `0004`, stand-in `ai_planning` claim, `tests/conftest.py` and
   `tests/test_entitlement.py`, README API section, root `.env.example` entitlement settings,
   these spec docs. Spec 008's demo web login keeps working (stand-in tokens grant access).
2. **Web PR**, branch `009-sign-in-access-web` (based on the backend branch): `frontend/`,
   `infra/keycloak/`, `docker-compose.yml`, README run and sign-in section.

## Project Structure

### Documentation (this feature)

```text
specs/009-sign-in-session-access/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api-auth.md      # backend API changes on top of spec 008
│   └── web-auth.md      # web settings, screens, shared client, Keycloak realm
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
# Backend PR
.env.example                             # + ENTITLEMENT_DENY, ENTITLEMENT_MODE
backend/
├── alembic/versions/0004_add_session_access.py   # new: access, access_checked_at
├── app/
│   ├── auth.py                          # + verified_claims; current_user depends on it
│   ├── entitlement.py                   # new: check_access(claims)
│   ├── agent.py                         # education_only in the agent request
│   ├── models.py                        # Session.access, access_checked_at
│   └── main.py                          # GET /api/me; access check on POST /api/chat
├── devtools/stand_in_idp.py             # tokens carry ai_planning: true
└── tests/
    ├── conftest.py                      # make_token adds ai_planning: True (None drops it)
    ├── test_stand_in_idp.py             # + checks the claim
    └── test_entitlement.py              # new: /api/me, 403, education_only, access stored

# Web PR
docker-compose.yml                       # + keycloak (8081); backend points at it; oidc service removed
infra/keycloak/convai-realm.json         # new: realm, two clients, mappers, test users
frontend/
├── packages/core/src/api.ts             # configureApi({getToken, onUnauthorized}), ApiError, getMe, education_only
├── packages/core/src/__tests__/api.test.ts
└── apps/web/
    ├── .env.example                     # new
    ├── package.json                     # + oidc-client-ts
    ├── silent-callback.html             # new: Vite entry (src/auth/silentCallback.ts)
    └── src/
        ├── auth/client.ts               # new: AuthClient seam
        ├── auth/oidc.ts                 # new: UserManager from settings, in-memory store
        ├── auth/AuthProvider.tsx        # new: state machine (data-model.md), resume save/restore
        ├── auth/resume.ts               # new: convai.resume
        ├── auth/useIdleTimeout.ts       # new: activity tracking, warning, timeout
        ├── auth/IdleWarning.tsx         # new: "Are you still there?" dialog
        ├── auth/LoginPage.tsx           # becomes the sign-in prompt (no fields; statuses)
        ├── auth/user.ts                 # now only the User type and display name
        ├── App.tsx                      # uses AuthProvider; /auth/callback handling
        ├── chat/ChatApp.tsx             # access from /api/me; notices; draft restore
        └── __tests__/                   # Auth, IdleTimeout, Access (new); Login, helpers (rewritten); fakeAuth
```

**Structure Decision**: The backend keeps spec 008's single identity dependency; `verified_claims`
exposes the claims the access check needs, and `current_user` still returns `sub`. A
host-supplied token (embedded case) needs nothing new on the backend. In the web app, all OIDC
code sits behind `auth/client.ts` and `AuthProvider`; `ChatApp` only receives the user, the access
result and `signOut`. The shared client stays provider-agnostic through `getToken`.

## Implementation phases

1. **Setup**: Keycloak service and realm file; web dependency; settings and `.env.example`
   files; migration `0004`.
2. **Foundational**: `verified_claims`; `make_token` claim default; core `configureApi`,
   `ApiError`, `getMe`; web auth seam and test fakes.
3. **Story 1 (P1)**: tests first; web sign-in prompt, callback, silent check on load, token on
   calls, name from the ID token, sign-out with end session, provider-down and failed sign-in
   messages. Backend ownership is spec 008's.
4. **Story 2 (P2)**: tests first; silent renewal; idle hook and warning dialog; timeout and
   session-ended states; resume save and restore; draft cleared on deliberate sign-out; 401
   during use → one renewal, then session-ended.
5. **Story 3 (P3)**: tests first; entitlement module and settings; `/api/me`; 403 when denied;
   education-only flag to agent and in response; access stored per session; web notices and
   disabled composer.
6. **Polish**: README, quickstart run including the Okta-by-settings check, backlog sheet POC
   progress rows for BL-001 and BL-055.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| `oidc-client-ts` (web dependency) | PKCE, token renewal, silent sign-in and end-session in one maintained library, provider-agnostic | `keycloak-js` or Okta's SDK tie the code to one provider (FR-002); writing the flow by hand is error-prone |
| Keycloak container (local service, replaces spec 008's `oidc` compose service) | Real OIDC provider with MFA, session idle limits and logout, so BL-001 and BL-055 can be shown before client Okta access | Spec 008's stand-in has no sign-in page, MFA, refresh or sign-out at the provider |
