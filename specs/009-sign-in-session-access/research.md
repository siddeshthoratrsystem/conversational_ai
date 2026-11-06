# Research: Customer Sign-In, Session Timeout and Access to AI Planning

Decisions behind [plan.md](./plan.md). Each one: decision, rationale, alternatives considered.
Decisions already made by spec 008 are referenced, not repeated (`specs/008-oidc-auth/research.md`).

## R1. Sign-in protocol and local stand-in

**Decision**: OpenID Connect, authorization code flow with PKCE, against a public client. Locally,
Keycloak 26.4 (`quay.io/keycloak/keycloak:26.4`, `start-dev --import-realm`) runs in docker
compose on port **8081** with a committed realm file. It replaces spec 008's `oidc` compose
service; `backend/devtools/stand_in_idp.py` and its tests stay.

**Rationale**: Okta is OIDC (backlog BL-001), so the same flow and settings shape work for both;
moving is a change of issuer, client ID and redirect URLs (FR-002). PKCE is the standard for
browser apps with no client secret. Keycloak gives real users, one-time codes (TOTP), session
idle limits, refresh tokens and logout, so timeout and re-auth can be tested for real. Port 8081
avoids the agent's usual `localhost:8080`.

**Alternatives**: spec 008's stand-in (password grant only: no sign-in page, MFA, refresh or
logout, so BL-055 can't be shown); an Okta developer tenant (needs an account outside the client
and would not match their tenant anyway); implicit flow (deprecated).

## R2. Browser sign-in library

**Decision**: `oidc-client-ts` 3.5.0 in the web app, wrapped in one small module
(`apps/web/src/auth/oidc.ts`) behind the `AuthClient` seam (`auth/client.ts`). The user store is
in memory (`InMemoryWebStorage`); the PKCE state store stays in `sessionStorage` (it must survive
the redirect and holds no tokens). `automaticSilentRenew` keeps an active customer signed in,
renewing 30 s before expiry.

**Rationale**: Maintained OIDC client with PKCE, refresh, silent renew and end-session support;
no framework lock-in. Keeping tokens in memory meets FR-003, replacing spec 008's token in
`localStorage`.

**Alternatives**: `keycloak-js` (ties the code to Keycloak, breaking FR-002 for Okta);
`@okta/okta-auth-js` (ties it to Okta and can't run locally against Keycloak); `react-oidc-context`
(an extra wrapper over the same library, not needed for one provider component).

## R3. Restoring the sign-in after a page reload

**Decision**: On load, try a silent sign-in (`signinSilent`, hidden iframe, `prompt=none`). If it
works, the customer goes straight to the chat; if not, the sign-in prompt is shown. The silent
callback is a small extra page, `silent-callback.html`, built by Vite.

**Rationale**: Tokens live in memory, so a reload loses them. The identity provider's own session
cookie lets a silent check succeed without showing anything. Locally Keycloak (`localhost:8081`)
and the app (`localhost:5173`) are the same site, so the iframe cookie is sent. With Okta in
production this depends on the custom domain; if third-party cookies are blocked, the fallback is
the sign-in prompt, which is still correct (one extra click).

**Alternatives**: storing tokens in `localStorage` (readable by any script on the page, fails
FR-003); a backend-for-frontend holding tokens in an HttpOnly cookie (better long term, noted for
the BFF discussion, but a bigger backend change than this spec needs).

## R4. Idle timeout and returning to the same conversation

**Decision**: The web app tracks activity (key, pointer, touch, focus, wheel) and shows the
warning at `idle - warning` (defaults 15 and 2 minutes, set by `VITE_IDLE_TIMEOUT_MINUTES` and
`VITE_IDLE_WARNING_MINUTES`). On timeout or a failed renewal it saves `{sessionId, draft}` to
`sessionStorage` under `convai.resume`, clears the screen and the in-memory tokens, ends the
provider session in a hidden frame, and shows the sign-in prompt with the reason. After the next
sign-in the saved state is read once and removed. A deliberate "Sign out" removes it and
redirects to the provider's end-session endpoint. Activity in other tabs is not shared.

**Rationale**: Meets FR-008, FR-009 and FR-011 without a server change. `sessionStorage` is per
tab and cleared when the tab closes, and the draft is the customer's own text, not a credential.
Keycloak's own SSO idle limit is set longer (30 minutes) so the app, not the provider, decides
the idle sign-out. Ending the provider session on timeout means a shared device needs the
password again.

**Alternatives**: relying on token expiry alone (no warning, and an active reader who is not
typing would be signed out); cross-tab activity sharing with `BroadcastChannel` (nice, not
required; can be added later).

## R5. Backend token check

**Decision**: Delivered by spec 008 (its R1–R12): PyJWT, keys from `OIDC_JWKS_URL`, `iss`, `aud`,
`exp`, `nbf`, `sub` checked with 60 s leeway, 401/503 with `{"detail"}`. Spec 009 only splits the
dependency: `verified_claims` returns the verified claims, and `current_user` depends on it and
still returns the `sub` string.

**Rationale**: The access check needs `ai_planning` and `preferred_username`, which `current_user`
doesn't expose. Splitting keeps one place that reads tokens, and no handler signature changes.

**Alternatives**: decoding the token a second time in the entitlement module (two places that
know about tokens).

## R6. Turning checking off for local development and tests

**Decision**: Dropped. There is no `AUTH_MODE` (backend) or `VITE_AUTH_MODE` (web) and no
`local-dev` user.

**Rationale**: Spec 008 rules out any setting that turns the check off. Backend tests sign their
own tokens; web tests replace the sign-in client; local development uses Keycloak or a token from
the `convai-dev-cli` client (R11).

## R7. Chat ownership

**Decision**: Delivered by spec 008 (its R8–R10): `sessions.user_id` (migration `0003`); another
user's or an ownerless chat answers 404 `session not found` on send and on history (and history
of an unknown chat is 404 too); feedback answers 404 `message not found`; `GET /api/sessions`
skips them. The web app shows its existing "Couldn't open that chat." with Retry on a history
404. Spec 009's owner check runs before the access check, so another user's chat is 404 whatever
the caller's access.

## R8. Entitlement stand-in and education-only mode

**Decision**: `app/entitlement.py` `check_access(claims)` returns `granted`, `denied` or
`unavailable`, in this order:

1. `ENTITLEMENT_DENY` (comma-separated `sub` or `preferred_username` values): denied.
2. `ENTITLEMENT_MODE=unavailable`: unavailable, to show and test the failure path.
3. Otherwise (`ENTITLEMENT_MODE=claim`, the default) the token's `ai_planning` claim: `true` is
   granted, `false` is denied, missing or not a boolean is unavailable (fail closed).

`GET /api/me` returns the result. `POST /api/chat` refuses **403** when denied (nothing stored, a
warning logged); when unavailable it answers, sends `"education_only": true` to the agent, and
returns `"education_only": true`. The result and time are stored on the session
(`sessions.access`, `sessions.access_checked_at`) on every turn. In Keycloak the claim comes from
a user attribute through a protocol mapper. Spec 008's stand-in adds `"ai_planning": true` to
its tokens, and the test `make_token` does the same by default, so spec 008's web login and tests
keep full access.

**Rationale**: Real rules come from the business later; a claim is how Okta would likely supply
them, and the deny list and forced-unavailable mode cover every test case. The agent ignores
unknown fields today, so the added field is safe; the agent work decides how to behave on it.

**Alternatives**: a separate entitlement service call (nothing to call yet); an allow list (the
claim already covers it); hiding the chat entirely when the check fails (fails FR-014).

## R9. Token on API calls, shared by web and mobile

**Decision**: `@convai/core` `configureApi({ baseUrl?, getToken?, onUnauthorized? })` changes only
the options passed. `getToken` may return a promise. On a 401, `onUnauthorized()` is awaited; if
it resolves `true` the request is retried once. Every non-2xx throws `ApiError` with `status`.
`getMe()` is added. This replaces spec 008's sync `getToken` and `void` `onUnauthorized`. The web
app's `onUnauthorized` tries one silent renewal and, if that fails, ends the session with "Your
session has ended" (resume saved, as in R4).

**Rationale**: FR-003, FR-017, FR-018: a host app can call `configureApi({ getToken })` with its
own token and skip the sign-in flow. Handling 401 once in the client avoids wrapping each call
site. `ApiError`'s message keeps today's `Request failed (<status>)`.

**Alternatives**: patching `fetch` globally (hidden, hard to test); passing the token to each
call (changes every call site and the mobile app).

## R10. Where settings live

**Decision**: Web: `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`, `VITE_OIDC_SCOPE`,
`VITE_IDLE_TIMEOUT_MINUTES`, `VITE_IDLE_WARNING_MINUTES` in `frontend/apps/web/.env.example`
(spec 008's `VITE_OIDC_TOKEN_URL` goes). Redirect URLs are built from `window.location.origin`.
Backend: spec 008's `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, plus `ENTITLEMENT_DENY` and
`ENTITLEMENT_MODE`, in the root `.env.example`.

**Rationale**: Matches the constitution (settings from environment variables, every one in
`.env.example`) and FR-002. Build-time Vite variables are enough for the POC.

**Alternatives**: runtime `config.json` now (useful, but its own backlog item).

## R11. Local tokens for curl, and compose settings

**Decision**: The realm has a second public client, `convai-dev-cli`, with direct access grants
only and the same `convai-api` audience and `ai_planning` mappers, so developers can get a token
with curl. It exists only in the local realm and is never set up in Okta. Compose points the
backend at Keycloak: `OIDC_ISSUER=http://localhost:8081/realms/convai` (the name the browser
sees, which is what the token carries), `OIDC_AUDIENCE=convai-api`,
`OIDC_JWKS_URL=http://keycloak:8081/realms/convai/protocol/openid-connect/certs` (fetched over
the compose network).

**Rationale**: Spec 008's README showed how to call the API by hand with a stand-in token; this
keeps that possible without a browser. Spec 008's separate `OIDC_JWKS_URL` setting is what lets
the backend run in compose while the issuer stays `localhost`.

**Alternatives**: enabling direct access grants on `convai-web` (would make the browser client
accept passwords, which Okta's would not).
