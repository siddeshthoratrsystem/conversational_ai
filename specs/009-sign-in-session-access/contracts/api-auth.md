# Contract: Chat API, access to AI planning (spec 009)

Changes to the backend API on top of spec 008. Everything not listed here is unchanged. New
response fields are additive (Principle I). Error bodies keep `{"detail": "<message>"}`.

## From spec 008 (unchanged, for reference)

Full contract: `specs/008-oidc-auth/contracts/auth-api.md`. Every `/api/*` route except
`/api/health` needs `Authorization: Bearer <access token>`.

| Case | Response |
|---|---|
| Header missing or not `Bearer <token>`; token invalid, expired, wrong `iss` or `aud`, no `sub` | **401** `{"detail": "missing or invalid bearer token"}` with `WWW-Authenticate` |
| Keys can't be fetched and none are cached | **503** `{"detail": "sign-in service unavailable, try again later"}` |
| Chat or history for another user's, an ownerless or (history) an unknown session | **404** `{"detail": "session not found"}` |
| Feedback on a message in a session the caller doesn't own | **404** `{"detail": "message not found"}` |

`GET /api/sessions` skips sessions the caller doesn't own.

## `GET /api/me` (new)

Who is signed in and what they may use. Read-only.

```json
{
  "user_id": "f3b1c2d4-…",
  "name": "Alice Example",
  "access": "granted"
}
```

- `user_id`: the token's `sub`.
- `name`: the `name` claim, else `preferred_username`, else `sub`.
- `access`: `"granted"` | `"denied"` | `"unavailable"` (research R8).

## `POST /api/chat` (changed)

Request: unchanged. Checks run in this order: token (spec 008), body (400), owner (spec 008's
404), then access.

| Case | Response |
|---|---|
| `access` is `denied` | **403** `{"detail": "AI planning is not available for this account"}`; agent not called, nothing stored; a warning is logged with the user id and session id |
| `access` is `unavailable` | Answered normally; the agent request body gains `"education_only": true`; the response has `"education_only": true` |
| `access` is `granted` | Unchanged |

Response (additive field, present only when access is `unavailable`):

```json
{
  "session_id": "…",
  "reply": "…",
  "intent": null,
  "message_id": 42,
  "education_only": true
}
```

`education_only` is left out otherwise (`response_model_exclude_unset`), so replies for customers
with access are exactly as before. The mock reply reports it too.

Agent request body (additive field, only when unavailable):

```json
{ "prompt": "…", "session_id": "…", "education_only": true }
```

Each answered turn sets `sessions.access` and `sessions.access_checked_at` in the same
transaction as the messages.

## Other endpoints

History, sessions and feedback: no change from spec 008. They don't run the access check.

## Settings (root `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` | none | From spec 008; all required |
| `ENTITLEMENT_DENY` | empty | Comma-separated `sub` or `preferred_username` values always denied |
| `ENTITLEMENT_MODE` | `claim` | `claim` uses the `ai_planning` claim; `unavailable` forces education only for everyone |

## Dev and test token changes

- Spec 008's stand-in (`backend/devtools/stand_in_idp.py`) adds `"ai_planning": true` to every
  token, so spec 008's demo web login keeps full access.
- `make_token` in `backend/tests/conftest.py` includes `ai_planning: True` by default; pass
  `ai_planning=None` to drop it.
