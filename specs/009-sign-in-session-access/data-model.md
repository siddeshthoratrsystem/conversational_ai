# Data Model: Customer Sign-In, Session Timeout and Access to AI Planning

## Database (migration `0004_add_session_access`)

Spec 008's migration `0003` added `sessions.user_id` (the owner). Spec 009's
`backend/alembic/versions/0004_add_session_access.py` (revises `0003`) adds two nullable columns.

### `sessions` (existing table)

| Column | Type | Rules |
|---|---|---|
| `user_id` | text, nullable | From spec 008: token `sub` of the customer who started the chat. `NULL` = no owner, seen by no one. |
| `access` | text, nullable (new) | Access result of the latest turn: `granted` or `unavailable` (R8). Set only through `app/entitlement.py`; no database constraint. `NULL` for chats from before this change. |
| `access_checked_at` | timestamptz, nullable (new) | When `access` was last decided. Set with `access` on every chat turn, in the same transaction as the messages. |

No other table changes. Ownership rules are spec 008's (`specs/008-oidc-auth/data-model.md`).

A denied customer's turn is refused before anything is stored, so `denied` never reaches the
table. It is recorded instead as a warning log line with the user id and session id (FR-015).

## Identity (not stored)

### Verified claims (backend, from `verified_claims`)

| Claim | Used for |
|---|---|
| `sub` | Customer id; `current_user` returns it; matched by `ENTITLEMENT_DENY`. |
| `name`, else `preferred_username`, else `sub` | `name` in `GET /api/me`. |
| `preferred_username` | Matched by `ENTITLEMENT_DENY`. |
| `ai_planning` | Boolean input to the access check; anything else counts as missing. |

### AccessResult

`granted` | `denied` | `unavailable`. Decided per request by `check_access(claims)` (R8).

## Browser state

| Key | Where | Holds | Lifetime |
|---|---|---|---|
| tokens (access, refresh, id) | memory only (`InMemoryWebStorage`) | sign-in proof | until reload, sign-out or timeout |
| `oidc.*` | `sessionStorage` (library) | PKCE verifier and state for the redirect | one sign-in round trip |
| `convai.resume` | `sessionStorage` | `{ "sessionId": string \| null, "draft": string }` | written on timeout or failed renewal; read once after sign-in, then removed; removed on deliberate sign-out |
| `convai.sessionIds` | `localStorage` (existing) | chat ids started in this browser | unchanged; the backend filters them by owner |
| `convai.user` | `localStorage` (spec 008 demo sign-in, with token) | demo username and token | no longer read or written |

## State: web sign-in

```text
starting ──silent sign-in ok──▶ signed-in
    │                              │  idle reaches (timeout − warning)
    └─silent fails──▶ signed-out   ▼
                        ▲        warning ──"Stay signed in"──▶ signed-in
                        │          │ time runs out
                        │          ▼
                        ├──── timed-out (resume saved)
                        ├──── session-ended (renewal or 401 failed; resume saved)
                        └──── "Sign out" (resume cleared, end session at provider)
signed-out ──"Sign in"──▶ provider ──callback──▶ signed-in (restore resume if any)
```

Every state except `signed-in` and `warning` shows no conversation content (FR-011).
