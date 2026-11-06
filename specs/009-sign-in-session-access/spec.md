# Feature Specification: Customer Sign-In, Session Timeout and Access to AI Planning

**Feature Branch**: `009-sign-in-session-access`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "Customer sign-in for the chat (backlog BL-001 Customer identity: Okta SSO and MFA, and BL-055 Session timeout and re-authentication, both P1 wave 1; workbook story C.8.3.1-S1 Session authentication and User entitlement; open item OI-06). Replace the demo sign-in in the web app with real OIDC sign-in. Until the client's Okta tenant is available, a local Keycloak in Docker stands in for Okta (with a test user and optional one-time-code MFA); moving to Okta must be a configuration change only (issuer, client ID, redirect URLs). The web app signs the customer in with OIDC (authorization code with PKCE), keeps the access token in memory, sends it on every API call, and refreshes it silently. When signed out, no personal data or chat history is shown; the customer sees a sign-in prompt. Sessions time out after an idle period (configurable); before signing out the customer gets a warning, and after signing in again they return to the same conversation with any unsent text kept. Sign out ends the session at the identity provider. The backend (FastAPI) validates the token (issuer, audience, signature via JWKS, expiry) on every /api call and rejects missing or invalid tokens with 401; sessions and history are scoped to the signed-in user, so one customer cannot see another's chats. Validation can be turned off by a setting for local development and tests. An entitlement check (stubbed for now: a claim or a config list) decides access to AI planning; customers without access get a plain message with a next step, and if the check fails the chat offers general education only (fail closed). The mobile app is out of scope for this spec beyond keeping the shared API client able to send a token. Embedding in Principal's host app with session handoff (no separate login) is a later step; the design should allow it by accepting a token from the host instead of running the sign-in flow."

**Revised 2026-11-06**: rebased on spec 008 (`specs/008-oidc-auth/`), which already delivers the
backend token check and per-user chats. The "validation can be turned off" part of the input is
dropped (see FR-016).

## Relationship to spec 008

Spec 008 (`specs/008-oidc-auth/`, on main) gave the backend token check on every `/api` call
except health, per-user chats (`sessions.user_id`; another user's chat is "not found") and a
dev-only stand-in identity provider with a demo password sign-in in the web app.

Spec 009 builds on it and adds:

- real sign-in in the web app: OIDC authorization code with PKCE (`oidc-client-ts`), token in
  memory, silent renewal, sign-out at the provider;
- Keycloak as the local stand-in for Okta, with a one-time-code (MFA) test user;
- idle timeout with a warning, and resume of the same chat and draft (BL-055);
- the AI-planning access check, with education-only fallback when it can't be decided.

Backlog: BL-001 (remaining parts: real sign-in screen, MFA), BL-055, workbook story
C.8.3.1-S1, OI-06.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign in and see only my own chats (Priority: P1)

A customer opens the chat and is asked to sign in through the company sign-in page (the same
kind of page they would use for their Principal account, including a one-time code when it is
turned on). After signing in, they land in the chat with their name shown. Their past chats
are listed, and only theirs. A person who is not signed in sees no chats, no history and no
personal details, only a prompt to sign in.

**Why this priority**: Nothing else in the product is safe to show without knowing who the
customer is. It completes BL-001 (P1, wave 1) on top of spec 008's backend check.

**Independent Test**: Sign in as test customer A, start a chat, sign out, sign in as test
customer B, and confirm B does not see A's chat and cannot open it, even by its address.

**Acceptance Scenarios**:

1. **Given** a person who is not signed in, **When** they open the chat, **Then** they see a sign-in prompt and no chat history, messages or personal details.
2. **Given** the sign-in prompt, **When** the customer signs in successfully, **Then** they return to the chat, see their own name, and their past chats are listed.
3. **Given** one-time-code verification is turned on for the customer, **When** they sign in, **Then** they must enter the code before reaching the chat.
4. **Given** a signed-in customer, **When** they start a chat and later reopen it, **Then** the full conversation is shown, as today.
5. **Given** two customers, **When** customer B lists or opens chats, **Then** customer A's chats never appear and opening one of A's chats directly is refused. (Backend rule delivered by spec 008; the web app shows "Couldn't open that chat.")
6. **Given** a request to the chat service without valid sign-in proof, **When** it reaches the service, **Then** it is refused, and nothing is stored or returned. (Delivered by spec 008.)
7. **Given** sign-in fails or is cancelled at the sign-in page, **When** the customer returns to the chat, **Then** they see a plain message and can try again.

---

### User Story 2 - Stay signed in safely, time out, and pick up where I left off (Priority: P2)

While the customer is active, they stay signed in without interruptions. If they leave the
chat idle, they are warned shortly before being signed out and can choose to stay. If they are
signed out for inactivity, signing in again takes them back to the same conversation, with any
message they had typed but not sent still in the box. Choosing "Sign out" signs them out fully,
so the next person on the device has to sign in again.

**Why this priority**: Required for a financial product on shared or unattended devices
(BL-055, P1, wave 1), but it builds on Story 1.

**Independent Test**: Set a short idle timeout, sign in, type a message without sending, wait
for the warning and let it expire, sign in again, and confirm the same conversation and the
typed text are back.

**Acceptance Scenarios**:

1. **Given** an active customer, **When** their sign-in would normally expire, **Then** it is renewed without asking them to sign in again.
2. **Given** a customer idle for the timeout period minus the warning period, **When** the warning appears, **Then** it says how long is left and offers "Stay signed in" and "Sign out".
3. **Given** the warning, **When** the customer chooses "Stay signed in", **Then** they stay signed in and the idle timer restarts.
4. **Given** the warning, **When** the time runs out, **Then** the customer is signed out, no conversation content stays on screen, and they see a message explaining why.
5. **Given** a customer signed out for inactivity, **When** they sign in again, **Then** they return to the conversation they were in, with any unsent text restored.
6. **Given** a signed-in customer, **When** they choose "Sign out", **Then** they are signed out of the chat and of the sign-in service, and returning to the chat asks them to sign in again.
7. **Given** renewal fails (for example, the sign-in service ended the session), **When** the customer next acts, **Then** they are asked to sign in again and return to the same conversation afterwards.

---

### User Story 3 - Only customers with access to AI planning get it (Priority: P3)

When a signed-in customer starts the chat, their access to AI planning is checked. Customers
with access get the full chat. Customers without access are told plainly that AI planning is
not available to them and what they can do next. If the check itself cannot be completed, the
chat stays safe: it offers general financial education only and says so.

**Why this priority**: Required by the workbook (User entitlement) and the backlog done criteria
for BL-001, but the rules come from the business later, so the check is a stand-in for now.

**Independent Test**: Sign in as a test customer marked without access and confirm the
message and next step; then make the check unavailable and confirm the education-only notice.

**Acceptance Scenarios**:

1. **Given** a signed-in customer with access, **When** the chat opens, **Then** the full chat is available with no extra notice.
2. **Given** a signed-in customer without access, **When** the chat opens, **Then** they see a plain message that AI planning is not available to them, with a next step (for example, contact support), and they cannot send planning questions.
3. **Given** the access check cannot be completed, **When** the chat opens, **Then** the customer sees a notice that only general education is available right now, planning shortcuts are hidden, and every message they send is marked as education-only for the assistant.
4. **Given** any of the above, **When** the result is decided, **Then** the outcome is recorded: access or check unavailable against the customer's session, no access in the service log (nothing is stored for a refused message).

---

### Edge Cases

- The sign-in service is down or unreachable: the customer sees a plain message with Retry; no chat content is shown.
- The customer's sign-in proof is tampered with, expired, issued by a different service, or meant for a different app: the chat service refuses it (spec 008).
- The customer opens the chat in two tabs: both work, and signing out in one signs out the other the next time it acts.
- The customer's account is disabled at the sign-in service while they are signed in: their next renewal fails and they are asked to sign in again.
- Chats created before spec 008 (no owner) are not shown to anyone (spec 008).
- The customer is redirected back from the sign-in page to a link that points outside the chat: the link is ignored and they land in the chat.
- The health check stays reachable without signing in (spec 008).
- Dropped: running with sign-in checking turned off. Spec 008's backend always checks, and tests make their own tokens.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The web chat MUST require the customer to sign in through the configured sign-in service before showing any chat content, history or personal details.
- **FR-002**: The sign-in service MUST be selected by configuration only (service address, app identifier, return addresses). Switching from the local stand-in to the client's service MUST NOT need code changes.
- **FR-003**: The web chat MUST include the customer's sign-in proof with every request to the chat service and MUST NOT store it where other sites or scripts on the device can read it after the tab is closed. (This replaces spec 008's demo, which kept the token in `localStorage`.)
- **FR-004**: Delivered by spec 008: the chat service refuses requests without valid sign-in proof; the health check is exempt.
- **FR-005**: Delivered by spec 008: each chat belongs to the customer who started it, and another customer's chat is answered as not found.
- **FR-006**: The customer's display name MUST come from the sign-in service, replacing the name typed on the demo sign-in page.
- **FR-007**: The customer's sign-in MUST be renewed in the background while they are active, without interrupting them.
- **FR-008**: After an idle period (default 15 minutes, configurable), the customer MUST be signed out. A warning MUST appear before that (default 2 minutes before, configurable) with "Stay signed in" and "Sign out".
- **FR-009**: After being signed out for inactivity or a failed renewal, signing in again MUST return the customer to the same conversation with any unsent text restored. Unsent text MUST be cleared on a deliberate "Sign out".
- **FR-010**: "Sign out" MUST end the session at the sign-in service as well as in the chat.
- **FR-011**: When signed out for any reason, no conversation content MUST remain visible on screen.
- **FR-012**: An access check MUST run when a signed-in customer opens the chat and on every message. Until the business supplies real rules, it uses a deny list, a setting that forces the check to fail, and a marker supplied by the sign-in service.
- **FR-013**: Customers without access MUST see a plain message and a next step, and MUST NOT be able to send planning questions.
- **FR-014**: If the access check cannot be completed, the chat MUST offer general education only: it shows a notice, hides planning shortcuts, and marks each message as education-only for the assistant (fail closed).
- **FR-015**: The access outcome MUST be recorded against the customer's session (a refused message is logged instead, since nothing is stored).
- **FR-016**: Dropped. There is no setting that turns sign-in checking off: spec 008 rules it out, and tests make their own tokens.
- **FR-017**: The design MUST allow a host app to supply the customer's sign-in proof directly (for the later embedded case), so the chat can skip its own sign-in step without other changes.
- **FR-018**: The shared client code used by web and mobile MUST be able to attach sign-in proof to requests (spec 008 added this; spec 009 lets the proof be fetched asynchronously and renewed once on refusal). Mobile sign-in itself is out of scope.
- **FR-019**: A local stand-in sign-in service with at least two test customers (one with access, one without) and optional one-time-code verification MUST be startable with one command, and its setup MUST be documented.
- **FR-020**: All sign-in, timeout and access screens MUST be keyboard operable, announced to assistive technology, and use the Principal theme.
- **FR-021**: The chat service contract changes in this spec (who is signed in and their access, the refusal for customers without access, the education-only marker) MUST be documented in the README, and new fields MUST be additive.

### Key Entities

- **Customer identity**: who is signed in, as stated by the sign-in service: a stable customer ID, display name and, when supplied, an access marker. Not stored by the chat beyond linking it to chats.
- **Chat session (existing)**: has an owner since spec 008; now also records its latest access result.
- **Access result**: access, no access or check unavailable. Access and check unavailable are recorded per chat session with the time they were decided.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A returning test customer can go from opening the chat to typing their first message in under 30 seconds, including sign-in.
- **SC-002**: Delivered by spec 008: 100% of requests without valid sign-in proof are refused in automated tests.
- **SC-003**: Delivered by spec 008: 0 cases in automated tests where one customer can list, open, continue or rate another customer's chat.
- **SC-004**: An active customer is never asked to sign in again during a 60-minute session of steady use.
- **SC-005**: After an inactivity sign-out, 100% of test runs return the customer to the same conversation with unsent text intact.
- **SC-006**: Switching to a different sign-in service is done by changing settings only, shown by running the app against the stand-in with two different setting files and no code change.
- **SC-007**: All existing frontend and backend tests still pass, and every scenario and edge case above has an automated test.

## Assumptions

- The client uses Okta, which follows the OpenID Connect standard (backlog BL-001). A local Keycloak in Docker stands in for it until the client's Okta tenant is available. It replaces spec 008's stand-in in docker compose, because that one can't show MFA, renewal or sign-out. The exact sign-in method, assurance levels and step-up rules are still open (OI-06); this spec covers sign-in with an optional one-time code.
- "No separate login" (workbook C.8.3.1-S1) applies once the chat is embedded in Principal's web or app (Start here, decision 4). Until then the chat runs its own sign-in; FR-017 keeps the embedded path open.
- Timeout defaults (15 minutes idle, 2-minute warning) are placeholders until Principal's security policy is known; both are settings.
- Step-up sign-in for sensitive actions is out of scope: there are no sensitive actions yet (Release 1 is read-only per the architecture diagram). It is noted for BL-037.
- Real entitlement rules come from the business later; the configured stand-in is enough to build and test both outcomes and the failure path.
- "Education only" is a marker passed to the assistant and shown in the UI; the agent's behavior under that marker is owned by the agent work, not this spec.
- The demo sign-in page is replaced; its look carries over to the sign-in prompt.
- The mobile app makes no API calls yet (spec 008); mobile sign-in is specified later.
- The backend is owned by Rajesh; the backend part of this spec is small and goes in its own pull request for his review.
