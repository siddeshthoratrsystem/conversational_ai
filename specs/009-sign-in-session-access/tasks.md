---

description: "Task list for spec 009: customer sign-in, session timeout and access to AI planning"
---

# Tasks: Customer Sign-In, Session Timeout and Access to AI Planning

**Input**: Design documents from `/specs/009-sign-in-session-access/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-auth.md, contracts/web-auth.md, quickstart.md

**Tests**: Required (constitution IV, SC-007). Write each story's tests first and confirm they fail. Existing backend and frontend tests must keep passing. Existing web test files other than `Login.test.tsx` and `helpers.ts` MUST NOT be edited; `signInAs()` in `helpers.ts` keeps its name and signature so they work unchanged.

**Organization**: Tasks are grouped by user story. This is a record of what was done, re-mapped onto spec 008 (`specs/008-oidc-auth/`). Tasks marked "Covered by spec 008" were planned here first and are delivered by spec 008 instead; tasks marked "Dropped" no longer apply.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3
- All paths are relative to the repository root

## Rules for every task

- Tokens live in memory only; nothing token-like goes in `localStorage` or `sessionStorage` (FR-003). Only `convai.resume` (`{sessionId, draft}`) and the library's PKCE state use `sessionStorage`.
- Error bodies are always `{"detail": "<message>"}` with the exact texts in `contracts/api-auth.md`.
- Ownership is spec 008's: another user's or an ownerless chat is 404 on send and history, skipped in lists, 404 on rate.
- Use theme tokens only; no hex colors outside `packages/tokens` (theme test enforces this). All new UI is keyboard operable with visible focus (FR-020).
- Tests need no Keycloak, Postgres or network.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Create `infra/keycloak/convai-realm.json` per contracts/web-auth.md "Local identity provider": realm `convai`; public client `convai-web` (standard flow only, PKCE `S256` required, redirect URIs and post-logout redirect `http://localhost:5173/*`, web origin `http://localhost:5173`); public client `convai-dev-cli` (direct access grants only, local only); on both, audience mapper adding `convai-api` and user-attribute mapper `ai_planning` → access-token claim `ai_planning` (boolean); access token 300 s, SSO idle 1800 s, SSO max 36000 s; users `alice` (`ai_planning=true`), `bob` (`ai_planning=false`), `carol` (`ai_planning=true`, required action `CONFIGURE_TOTP`), each with first and last name, email and password `<username>-test` (local test values only)
- [X] T002 In `docker-compose.yml`: add a `keycloak` service (image `quay.io/keycloak/keycloak:26.4`, command `start-dev --import-realm --http-port=8081`, port `8081:8081`, `KC_BOOTSTRAP_ADMIN_USERNAME`/`KC_BOOTSTRAP_ADMIN_PASSWORD` defaulting to local `admin`/`admin`, volume `./infra/keycloak:/opt/keycloak/data/import:ro`); point the backend at it (`OIDC_ISSUER=http://localhost:8081/realms/convai`, `OIDC_AUDIENCE=convai-api`, `OIDC_JWKS_URL=http://keycloak:8081/realms/convai/protocol/openid-connect/certs`, pass `ENTITLEMENT_DENY` and `ENTITLEMENT_MODE` through); remove spec 008's `oidc` service (the devtools module and its tests stay)
- [X] T003 Start Keycloak and verify `curl -s http://localhost:8081/realms/convai/.well-known/openid-configuration` returns the issuer `http://localhost:8081/realms/convai`
- [X] T004 Covered by spec 008: `pyjwt[crypto]` is already in `backend/requirements.txt`
- [X] T005 [P] Web dependency: `npm install oidc-client-ts@^3.5.0 -w @convai/web` in `frontend/`
- [X] T006 [P] Add `ENTITLEMENT_DENY=` and `ENTITLEMENT_MODE=claim` to the root `.env.example` (spec 008's file), each with a one-line comment. `OIDC_*` are spec 008's; the web PR switches their example values to the local Keycloak and drops `VITE_OIDC_TOKEN_URL`. (`AUTH_MODE` dropped: no off mode.)
- [X] T007 [P] Create `frontend/apps/web/.env.example` with `VITE_OIDC_AUTHORITY=http://localhost:8081/realms/convai`, `VITE_OIDC_CLIENT_ID=convai-web`, `VITE_OIDC_SCOPE=openid profile`, `VITE_IDLE_TIMEOUT_MINUTES=15`, `VITE_IDLE_WARNING_MINUTES=2`; declare them in `frontend/apps/web/src/vite-env.d.ts` (`ImportMetaEnv`). (`VITE_AUTH_MODE` dropped.)
- [X] T008 Create migration `backend/alembic/versions/0004_add_session_access.py` (revises `0003`): nullable `sessions.access` (text) and `sessions.access_checked_at` (timestamptz); downgrade drops them. Add both to `Session` in `backend/app/models.py`. (The owner column is spec 008's `user_id`, migration `0003`.)

**Checkpoint**: Keycloak runs with the realm; dependencies, settings and schema are in place; all existing tests still pass.

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T009 Token check covered by spec 008 (`backend/app/auth.py`). Spec 009 splits the dependency: `verified_claims` returns the verified claims; `current_user` depends on it and still returns `sub`. (`AUTH_MODE`, `LOCAL_DEV_USER` and the `CurrentUser` dataclass dropped.)
- [X] T010 Test keys, `make_token` and the default `client` with alice's token covered by spec 008 (`backend/tests/conftest.py`). Spec 009: `make_token` includes `ai_planning: True` by default (`ai_planning=None` drops it); the stand-in (`backend/devtools/stand_in_idp.py`) adds `"ai_planning": true` to its tokens, checked in `tests/test_stand_in_idp.py`
- [X] T011 [P] In `frontend/packages/core/src/api.ts`: `configureApi({ baseUrl?, getToken?, onUnauthorized? })` changes only the options passed; `getToken` may be async; on 401 await `onUnauthorized()` and retry once if it resolves `true`; export `class ApiError extends Error { status: number }` thrown for every non-2xx with message `Request failed (<status>)`; add `type Me` and `getMe()`; add `education_only?: boolean | null` to `ChatResponse` (contracts/web-auth.md). Replaces spec 008's sync `getToken` and `void` `onUnauthorized`. Tests first in `frontend/packages/core/src/__tests__/api.test.ts`
- [X] T012 Create the auth client seam in `frontend/apps/web/src/auth/client.ts`: interface `AuthClient` (`signInSilent`, `signInRedirect`, `handleCallback`, `renew`, `signOut`, `forget`, `getAccessToken`, `getUserName`, `onRenewFailed`); `getAuthClient()` returns the OIDC client by default (T013) and `setAuthClient(client)` for tests. (`authMode()` dropped.)
- [X] T013 Create `frontend/apps/web/src/auth/oidc.ts`: `AuthClient` over `oidc-client-ts` `UserManager` with `authority`/`client_id`/`scope` from env, `redirect_uri = origin + "/auth/callback"`, `silent_redirect_uri = origin + "/silent-callback.html"`, `post_logout_redirect_uri = origin + "/"`, `response_type: "code"`, `userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() })`, `automaticSilentRenew: true`. Create `frontend/apps/web/silent-callback.html` loading `src/auth/silentCallback.ts` (handles silent sign-in and silent sign-out answers); add both HTML files to `build.rollupOptions.input` in `frontend/apps/web/vite.config.ts`
- [X] T014 Create a fake `AuthClient` for tests in `frontend/apps/web/src/__tests__/fakeAuth.ts` (configurable session and token, records calls, triggers renew failure, can make `signInSilent` throw). Update `signInAs()` in `helpers.ts` to install the fake as signed in (same name and signature; no `localStorage`). Extend the fake backend additively: `GET /api/me` (`{user_id, name, access}` from `Server.me`), records the `Authorization` header, `Server.rejectAuth` → 401, `Server.access` drives 403 and `education_only`
- [X] T015 Verify: backend `pytest`; in `frontend/`: `npx tsc -b`, `npm test`, `npm run build`

**Checkpoint**: The backend exposes verified claims; web has an auth seam and test fakes.

---

## Phase 3: User Story 1 - Sign in and see only my own chats (Priority: P1) 🎯 MVP

**Goal**: Only signed-in customers see anything, and each sees only their own chats.

**Independent Test**: quickstart Manual 1–3; automated tests below.

### Tests for User Story 1 (write first, confirm they fail)

- [X] T016 [P] [US1] Covered by spec 008: `backend/tests/test_auth.py` (401 and 503 cases, health open, settings required). The `/api/me` tests are in `test_entitlement.py` (T035). (`AUTH_MODE` cases dropped.)
- [X] T017 [P] [US1] Covered by spec 008: `backend/tests/test_ownership.py` (404 on another user's history, send and feedback; skipped in lists; ownerless chats invisible)
- [X] T018 [P] [US1] Rewrite `frontend/apps/web/src/__tests__/Login.test.tsx` for the sign-in prompt (contracts/web-auth.md "Screens"): signed out shows heading "Sign in to Alfred", button "Sign in", and no chat, history or composer; "Sign in" calls `signInRedirect`; a silent sign-in shows the chat without the prompt; at `/auth/callback` the callback is handled and the URL is replaced with `/`; a failed callback shows "Sign-in didn't complete." with "Try again"; `signInSilent` throwing shows "We can't reach the sign-in service right now." with "Try again"; the header shows "Signed in as <name>"; "Sign out" signs out at the provider; every API call carries `Authorization: Bearer <fake token>`. (Checking-off cases dropped.)
- [X] T019 [P] [US1] `frontend/apps/web/src/__tests__/Auth.test.tsx`: a 401 during use triggers one `renew`; if it succeeds the call is retried once; if it fails the screen clears to the sign-in prompt with "Your session has ended. Sign in to continue."

### Implementation for User Story 1

- [X] T020 [US1] Ownership covered by spec 008 (`backend/app/main.py`). `GET /api/me` is added in T038.
- [X] T021 [US1] Covered by spec 008: feedback owner check in `backend/app/feedback.py`
- [X] T022 [US1] Covered by spec 008: its backend tests pass on main
- [X] T023 [US1] Create `frontend/apps/web/src/auth/AuthProvider.tsx`: state per data-model.md (`starting`, `signed-out` with optional `reason` of `failed` / `unreachable` / `timed-out` / `session-ended`, `signed-in`); on mount: at `/auth/callback` run `handleCallback` then `history.replaceState` to `/`, else `signInSilent`; `configureApi({ getToken, onUnauthorized })` (renew once, else `endSession("session-ended")`); exposes `signIn()`, `retry()`, `signOut()` and `endSession(reason)`. (Off mode dropped.)
- [X] T024 [US1] Turn `frontend/apps/web/src/auth/LoginPage.tsx` into the sign-in prompt: keep the Alfred layout, logo and card; remove the username and password fields and the demo notice; one "Sign in" button; status or alert line for each `reason` with exact texts from contracts/web-auth.md and "Try again" for `failed` and `unreachable`; `role="status"` for informational lines, `role="alert"` for errors
- [X] T025 [US1] Update `frontend/apps/web/src/App.tsx` to render `AuthProvider` and, by state, a "Signing in…" status (`starting`), the sign-in prompt (`signed-out`) or `ChatApp` (`signed-in`). Cut `frontend/apps/web/src/auth/user.ts` down to the `User` type and display-name helpers (spec 008's token storage removed)
- [X] T026 [US1] Update `frontend/apps/web/src/chat/ChatApp.tsx` and `chat/AlfredHeader.tsx`: name from the ID token ("Signed in as <name>"), access from `getMe()`, "Sign out" calls the context's `signOut`. (Checking-off tag dropped.)
- [X] T027 [US1] Run web tests: T018, T019 and all existing web tests pass; `npx tsc -b` and `npm run build` succeed

**Checkpoint**: Story 1 works end to end against Keycloak (quickstart Manual 1–3, 9).

---

## Phase 4: User Story 2 - Stay signed in, time out, pick up where I left off (Priority: P2)

**Goal**: Silent renewal while active; idle warning and sign-out; return to the same chat and draft.

**Independent Test**: quickstart Manual 4–6.

### Tests for User Story 2 (write first, confirm they fail)

- [X] T028 [P] [US2] `frontend/apps/web/src/__tests__/IdleTimeout.test.tsx` (fake timers, settings 15 / 2 min): no dialog before 13 min of no activity; activity resets the timer; at 13 min the dialog "Are you still there?" opens with focus inside and text "You'll be signed out in 2:00." counting down; "Stay signed in" and Escape close it and restart the timer; "Sign out" in the dialog signs out like the header button; at 15 min the screen clears and the prompt says "You were signed out after 15 minutes of inactivity."; the minutes come from the settings
- [X] T029 [P] [US2] Add to `IdleTimeout.test.tsx`: on timeout `convai.resume` holds the open `sessionId` and the unsent draft; after signing in again that chat is opened and the draft is in the message box, then `convai.resume` is removed; the same after a failed renewal with the "session has ended" text; a deliberate "Sign out" removes `convai.resume`; a new chat with no messages saves only the draft; an unreadable `convai.resume` is ignored

### Implementation for User Story 2

- [X] T030 [US2] Create `frontend/apps/web/src/auth/useIdleTimeout.ts`: tracks `keydown`, `pointerdown`, `touchstart`, `focusin` and `wheel` on `window`, exposes `{ secondsLeft, stay() }`, calls `onTimeout()` at the timeout; reads minutes from `VITE_IDLE_TIMEOUT_MINUTES` / `VITE_IDLE_WARNING_MINUTES` (defaults 15 / 2); active only while signed in
- [X] T031 [US2] Create `frontend/apps/web/src/auth/IdleWarning.tsx`: accessible modal dialog (`role="dialog"`, `aria-modal`, labelled by its heading, focus trapped, Escape = stay) using `@convai/ui` Button and Card; texts per contracts/web-auth.md
- [X] T032 [US2] Resume state in `frontend/apps/web/src/auth/resume.ts`: `saveResume`, `takeResume` (read once, remove, ignore bad JSON or blocked storage), `clearResume`. `ChatApp` registers a resume source with the provider; `endSession(reason)` saves it before clearing; `signOut()` clears; after sign-in `ChatApp` reads `takeResume()` once and opens that session and restores the draft
- [X] T033 [US2] In `AuthProvider`: `onRenewFailed` → `endSession("session-ended")`; mount `useIdleTimeout` and `IdleWarning` when signed in, `onTimeout` → `endSession("timed-out")`
- [X] T034 [US2] Run web tests: T028, T029 and all earlier tests pass

**Checkpoint**: Stories 1 and 2 work (quickstart Manual 4–6).

---

## Phase 5: User Story 3 - Only customers with access get AI planning (Priority: P3)

**Goal**: Access check with stand-in rules; denied gets a message; unavailable gets education only.

**Independent Test**: quickstart Manual 7–8.

### Tests for User Story 3 (write first, confirm they fail)

- [X] T035 [P] [US3] `backend/tests/test_entitlement.py`: `/api/me` returns `user_id`, `name` (falls back to `preferred_username`, then `sub`) and needs a token; `ai_planning=true` → granted, `false` → denied, missing or non-boolean → unavailable; `ENTITLEMENT_DENY` by `sub` and by `preferred_username` → denied even with the claim true; `ENTITLEMENT_MODE=unavailable` → unavailable; denied `POST /api/chat` → 403 `AI planning is not available for this account`, nothing stored, warning logged; unavailable chat → `education_only: true` in the reply and the agent body, session row `access="unavailable"` with `access_checked_at`; granted chat → no `education_only` key in the reply or the agent body, `access="granted"`; access updated on every turn; mock reply also reports `education_only`; another user's chat is still 404 before the access check
- [X] T036 [P] [US3] `frontend/apps/web/src/__tests__/Access.test.tsx`: `access: "denied"` → notice "AI planning isn't available for your account." with the next step, message box and suggestion cards disabled, no `POST /api/chat` sent; `access: "unavailable"` → notice "Right now Alfred can only answer general financial education questions.", suggestion cards hidden, sending works; `access: "granted"` → no notice; a 403 on send shows the denied notice

### Implementation for User Story 3

- [X] T037 [US3] Create `backend/app/entitlement.py`: `check_access(claims) -> Literal["granted","denied","unavailable"]` per research R8 (deny list, then forced unavailable, then the boolean `ai_planning` claim, fail closed)
- [X] T038 [US3] In `backend/app/main.py`: new `GET /api/me` (`verified_claims`; `{user_id, name, access}`); `POST /api/chat` runs the owner check (404) first, then `check_access`: denied → warning log and 403; otherwise pass `education_only` to `_reply_for` and `call_agent`, set `sessions.access` and `access_checked_at` in `_persist`'s transaction, and return `education_only` only when true (`response_model_exclude_unset`). In `backend/app/agent.py` add `education_only: bool = False` to `call_agent` and include `"education_only": true` in the body only when true
- [X] T039 [US3] Web: in `ChatApp.tsx` read `me.access`; render the notices (`role="status"`) above the composer; denied disables the composer and the Welcome suggestion cards; unavailable hides the suggestion cards; a 403 from `sendMessage` switches to the denied notice. Next-step text "Contact Principal support for help." (placeholder until the business supplies it; noted in the README)
- [X] T040 [US3] Run tests: T035, T036 and everything earlier pass (backend and web)

**Checkpoint**: All three stories work (quickstart Manual 7–8).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T041 [P] README: API section (backend PR): `GET /api/me`, the 403, `education_only` in the reply and the agent body, the entitlement settings. Run and "Sign-in (specs 008 and 009)" section (web PR): compose with Keycloak, the three test users, a curl token from `convai-dev-cli`, the settings table, moving to Okta by settings
- [X] T042 [P] Accessibility pass on the sign-in prompt, warning dialog and notices with keyboard only (quickstart Manual 12); fix any focus or labelling gaps and add a test for each fix
- [X] T043 Run the full quickstart (Manual 1–12) against Keycloak, the backend and Postgres, including the second realm for SC-006; record any deviations under "Notes"
- [X] T044 Final check: `cd backend && .venv/bin/pytest`; `cd frontend && npx tsc -b && npm test && npm run build`; report the counts
- [ ] T045 Add POC progress rows for BL-001 and BL-055 to `docs/architecture/architecture-backlog.xlsx` ("POC progress" tab: backlog item, task, owner Vinod, progress, date) only if the sheet's owner agrees; otherwise list the suggested rows in the PR description

---

## Dependencies & Execution Order

- **Setup (T001–T008)**: T001 → T002 → T003; T005–T007 in parallel; T008 any time.
- **Foundational (T009–T015)**: T009 → T010; T011 parallel to backend work; T012 → T013; T014 after T011 and T012. Blocks all stories.
- **US1 (T016–T027)**: backend half is spec 008's; web T023 → T024 → T025 → T026 → T027.
- **US2 (T028–T034)**: needs US1's `AuthProvider` and `ChatApp` wiring.
- **US3 (T035–T040)**: backend needs only T009–T010; web needs US1.
- **Polish (T041–T045)**: after the stories.

### Parallel examples

```text
Setup:        T005 (web dep) | T006 (.env.example) | T007 (web env) | T008 (migration)
US1 tests:    T018 (Login.test.tsx) | T019 (Auth.test.tsx)
US3 tests:    T035 (test_entitlement.py) | T036 (Access.test.tsx)
```

## Implementation Strategy

1. **Backend PR** (branch `009-sign-in-access-backend`, on main): T006, T008–T010, T035, T037, T038, T041 (API section), and these spec docs. Spec 008's demo login keeps full access because stand-in tokens carry `ai_planning: true`. Rajesh reviews.
2. **Web PR** (branch `009-sign-in-access-web`, on the backend branch): T001–T003, T005, T007, T011–T019, T023–T034, T036, T039, T041 (run and sign-in section), T042. Vinod owns; Rajesh reviews the compose change.
3. MVP is US1 (real sign-in on spec 008's check); US2 closes BL-055; US3 meets BL-001's done criteria.

---

## Notes (implementation, 2026-11-06)

Results after the rebase: backend 192 tests pass (172 from spec 008 + 20 in `test_entitlement.py`); frontend web 117, core 18, tokens 4; type check and build pass. Quickstart Manual 1–9, 11 and 12 were run in headless Chrome against Keycloak, the host backend and Postgres on the first (pre-rebase) build. On the rebased build, re-run with Keycloak tokens: `/api/me` (alice granted, bob denied), chat 200 for alice and 403 for bob, 404 for bob reading alice's chat, 401 without a token, access stored on the session; and in headless Chrome: sign-in, reload, sign-out at the provider, bob's no-access notice and empty history. The idle timeout and resume were not re-run in the browser (unchanged code; covered by `IdleTimeout.test.tsx`).

Rebased on spec 008 (planned here as spec 008, `008-oidc-sign-in`, built in parallel with `specs/008-oidc-auth/`):

- **Spec 008's backend is kept as is.** Token check, settings, 401/503 texts, `sessions.user_id` and the 404 rules are spec 008's. Our planned `owner_id` column, the empty-list history for other users' chats, and our own `auth.py` were dropped.
- **No sign-in-checking-off mode.** `AUTH_MODE`, `VITE_AUTH_MODE`, the `local-dev` user, `auth` in `/api/me` and the "Sign-in checking off" tag were dropped. Tests make their own tokens; developers use Keycloak or the `convai-dev-cli` client.
- **Migration `0004`** adds only `access` and `access_checked_at`.
- **The stand-in stays out of compose.** Keycloak replaces the `oidc` service; `stand_in_idp.py` stays and now grants `ai_planning`.

Deviations from the first plan, all reflected in the contracts:

- **Name from the sign-in token.** The header and greeting take the name from the ID token, not from `GET /api/me`, so the chat shows at once. `/api/me` is used for the access result.
- **`AuthClient` shape (T012).** Final methods as listed in T012. A 401 is handled in `@convai/core` through `configureApi({ onUnauthorized })` (renew once, retry once), instead of wrapping each call site.
- **`education_only` is left out unless true**, in the reply and the agent request, so existing exact-body tests stay unchanged.
- **Found in the quickstart run and fixed:** (1) after an idle sign-out, the Keycloak session stayed alive, so anyone could sign straight back in on a shared device; a lost session now also ends the provider session in a hidden frame (`forget()` → `signoutSilent`), and the silent page handles both answers. (2) Renewal fired constantly with very short tokens; it now starts 30 s before expiry.
- **T045 not done:** the backlog sheet was not edited. Suggested POC progress rows: `BL-001 Customer identity | OIDC sign-in with Keycloak stand-in (MFA test user) and AI-planning access check, on spec 008's token check and chat ownership | Vinod | Partial (Okta tenant pending) | 2026-11-06` and `BL-055 Session timeout and re-authentication | Silent renewal, idle warning and sign-out, resume chat and draft | Vinod | Done (POC) | 2026-11-06`.
