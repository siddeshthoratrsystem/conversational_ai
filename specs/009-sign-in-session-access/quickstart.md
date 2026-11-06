# Quickstart: validate spec 009

Needs both PRs (backend and web). Spec 008's own checks are in `specs/008-oidc-auth/quickstart.md`.

## Prerequisites

- Docker running. `docker compose up --build` starts Postgres, Keycloak (port 8081) and the
  backend (port 8000, pointed at Keycloak). First start imports
  `infra/keycloak/convai-realm.json`; wait until
  `curl -s http://localhost:8081/realms/convai/.well-known/openid-configuration` returns JSON.
  (On this team's machines Postgres may run as `convai-db` on port 5433 when 5432 is taken.)
- Web: `cd frontend && npm install && npm run web` (defaults already point at the local realm).

Test users (local realm only, see [contracts/web-auth.md](./contracts/web-auth.md)):
`alice` (has access), `bob` (no access), `carol` (has access, one-time code). The password for
each is the username followed by `-test`, e.g. `alice-test`.

## Automated

```bash
cd backend && .venv/bin/pytest
cd frontend && npx tsc -b && npm test && npm run build
```

Both run with no Keycloak, Postgres or network.

## Manual

1. **Signed out**: open http://localhost:5173 in a private window. You see "Sign in to Alfred"
   and no chats. `curl -i localhost:8000/api/sessions` returns 401 (spec 008).
2. **Sign in**: click Sign in, sign in as `alice`. You are back in the chat; the header says
   "Signed in as Alice". Send a message.
3. **Ownership**: sign out (you land on the sign-in prompt, and the Keycloak account page at
   `http://localhost:8081/realms/convai/account` also asks you to sign in). Sign in as `carol`:
   you must set up and enter a one-time code (any TOTP app). Alice's chat is not in History.
   Check the database:
   `docker compose exec db psql -U app convai -c "select id, user_id, access from sessions order by created_at desc limit 3;"`
4. **Silent renewal**: stay active for 10 minutes (access tokens last 5). You are never asked to
   sign in; the Network tab shows token refreshes.
5. **Timeout**: restart the web app with `VITE_IDLE_TIMEOUT_MINUTES=2 VITE_IDLE_WARNING_MINUTES=1`.
   Sign in, type a message without sending, and wait. After 1 minute the "Are you still there?"
   dialog appears; "Stay signed in" closes it. Wait again and let it run out: the screen clears
   and says you were signed out after 2 minutes. Sign in (the password is asked again): the same
   chat is open and your typed text is in the box.
6. **Sign out clears**: type a draft, click Sign out, sign in again: the draft is gone.
7. **No access**: sign in as `bob`. The notice says AI planning isn't available, with the next
   step; the message box is disabled. `POST /api/chat` with Bob's token returns 403.
8. **Check unavailable**: `ENTITLEMENT_MODE=unavailable docker compose up -d backend`. Sign in as
   `alice`: the education-only notice shows, the suggestion cards are gone, and replies come back
   with `"education_only": true`.
9. **Provider down**: `docker compose stop keycloak`, reload the page: "We can't reach the
   sign-in service right now" with Try again. Start it again and retry.
10. **Token by hand**: get a token from the `convai-dev-cli` client and call `POST /api/chat`
    with curl, as in the README "Sign-in" section. `GET /api/me` with Bob's token says
    `"access": "denied"`.
11. **Okta by settings only (SC-006)**: copy the realm under a second name (`convai2`, client
    `convai-web-2`), point `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`, `OIDC_ISSUER` and
    `OIDC_JWKS_URL` at it, and sign in. No code change.
12. **Keyboard**: tab through the sign-in prompt, the warning dialog and the notices: each has a
    visible focus ring, the dialog keeps focus inside it, and Escape means "Stay signed in".
