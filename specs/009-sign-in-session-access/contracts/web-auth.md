# Contract: Web sign-in, shared API client and local identity provider (spec 009)

## `@convai/core` API client

Replaces spec 008's `configureApi` options (sync `getToken`, `void` `onUnauthorized`).

```ts
configureApi(options: {
  baseUrl?: string;
  getToken?: () => string | null | Promise<string | null>;
  onUnauthorized?: () => Promise<boolean>;
}): void
```

- Only the options passed are changed; `configureApi({ baseUrl })` behaves as today (mobile app
  unchanged).
- When `getToken` returns a token (awaited), every request sends `Authorization: Bearer <token>`.
- On a 401, `onUnauthorized()` is awaited; if it resolves `true`, the request is retried once
  with a fresh token.
- A host app that already has the customer's token (embedded case, FR-017) calls
  `configureApi({ getToken })` and does not use the web sign-in flow.

```ts
class ApiError extends Error { status: number }
```

Every non-2xx response throws `ApiError` (message unchanged: `Request failed (<status>)`), so
existing `catch` blocks keep working and new code can read `status`.

```ts
type Me = { user_id: string; name: string; access: "granted" | "denied" | "unavailable" }
getMe(): Promise<Me>
```

`ChatResponse` gains optional `education_only?: boolean | null` (present and `true` only in
education-only mode).

## Web app settings (`frontend/apps/web/.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `VITE_OIDC_AUTHORITY` | `http://localhost:8081/realms/convai` | Issuer URL |
| `VITE_OIDC_CLIENT_ID` | `convai-web` | Public client id |
| `VITE_OIDC_SCOPE` | `openid profile` | Requested scopes |
| `VITE_IDLE_TIMEOUT_MINUTES` | `15` | Idle sign-out |
| `VITE_IDLE_WARNING_MINUTES` | `2` | Warning shown this long before |

Redirect URIs come from the page origin: `<origin>/auth/callback` (sign-in),
`<origin>/silent-callback.html` (silent renew and reload check), `<origin>/` (after sign-out).
Moving to Okta means changing `VITE_OIDC_AUTHORITY` and `VITE_OIDC_CLIENT_ID`, the backend's
three `OIDC_*` settings, and registering these three URIs in Okta. No code change.

## Screens and labels (for tests and accessibility)

| State | What shows | Key accessible names |
|---|---|---|
| signed out | Sign-in prompt in the Alfred style, no chat content | heading "Sign in to Alfred", button "Sign in" |
| timed out | Sign-in prompt plus status message | "You were signed out after 15 minutes of inactivity." (minutes from settings) |
| session ended | Sign-in prompt plus status message | "Your session has ended. Sign in to continue." |
| sign-in failed or cancelled | Sign-in prompt plus alert with Retry | "Sign-in didn't complete.", button "Try again" |
| provider unreachable | Sign-in prompt plus alert with Retry | "We can't reach the sign-in service right now.", button "Try again" |
| warning | Modal dialog, focus moved into it | dialog "Are you still there?", text "You'll be signed out in M:SS.", buttons "Stay signed in", "Sign out" |
| access denied | Chat frame with notice, composer and suggestions disabled | "AI planning isn't available for your account.", next step "Contact Principal support for help." (placeholder) |
| education only | Notice above composer, planning suggestion cards hidden | "Right now Alfred can only answer general financial education questions." |
| chat can't be opened (history 404, spec 008) | Existing error with Retry | "Couldn't open that chat." |

The signed-in header shows the name from the ID token ("Signed in as <name>") and "Sign out";
`GET /api/me` supplies the access result. A 403 on send switches to the denied notice.

## Local identity provider (Keycloak)

Service `keycloak` in `docker-compose.yml`, image `quay.io/keycloak/keycloak:26.4`, port `8081`,
realm file `infra/keycloak/convai-realm.json` imported at start. Spec 008's `oidc` compose service
is removed (the devtools module and its tests stay).

| Item | Value |
|---|---|
| Realm | `convai` |
| Client `convai-web` | public, standard flow only, PKCE `S256` required; redirect URIs and post-logout redirect `http://localhost:5173/*`; web origin `http://localhost:5173` |
| Client `convai-dev-cli` | local only: public, direct access grants only, same audience and claim mappers; for getting a token with curl (README) |
| Audience | Mapper adds `convai-api` to the access token `aud` |
| Claim | Mapper puts user attribute `ai_planning` into the access token as boolean `ai_planning` |
| Lifetimes | Access token 5 min; SSO idle 30 min; SSO max 10 h |
| Test users | `alice` (`ai_planning=true`), `bob` (`ai_planning=false`), `carol` (`ai_planning=true`, one-time code set up on first sign-in) |

Compose backend settings: `OIDC_ISSUER=http://localhost:8081/realms/convai`,
`OIDC_AUDIENCE=convai-api`,
`OIDC_JWKS_URL=http://keycloak:8081/realms/convai/protocol/openid-connect/certs`.

Test user passwords are `<username>-test`, test values for this local realm only; they are in the
realm file and the quickstart, and must never be used anywhere else.
