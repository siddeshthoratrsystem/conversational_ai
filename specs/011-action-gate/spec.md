# Feature Specification: Action Gate for Agent Write Actions (Mock 401(k) Contribution Change)

**Feature Branch**: `011-action-gate`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Action gate for agent write actions (backlog BL-037), demonstrated with a mock 401(k) contribution change. No action runs without explicit participant confirmation and within agreed limits; confirmation is recorded. Real contribution changes are out of scope (BL-061: real changes are on hold until the client decides whether contribution changes are in scope), so the demo changes mock data only." The full description (participant experience, rules, demo data, notes for the plan step, out of scope, success) is captured in the sections below; the plan-step notes are kept in "Notes for the plan step".

## Relationship to other specs

- **Spec 005 (wealth agent)**: Impacts spec 005 (adds the first write tool and per-user data);
  its risk tier needs review by the spec 005 owner. This spec does not change spec 005 and
  keeps to its rules: figures come from code, not the model; the disclaimer is appended in
  code; tool output is treated as data.
- **Specs 008 and 009 (sign-in and access)**: the back end verifies who is signed in and
  checks their access to AI planning. Participants without access are refused by the back end
  and never reach the agent. When the access check can't be completed, the back end marks the
  message as education-only for the agent. The agent ignores that marker today; this spec makes
  the gate honour it for actions only. The agent's other behaviour is not changed by this spec.
  The back end also forwards the participant's sign-in token to the agent, and the agent runtime
  verifies it itself before the gate acts (BL-001).

Backlog: BL-037 (action gate; layer: agent runtime) and BL-001 (the agent runtime validates the
token before any agent runs).

Client requirement: Feature listv03, "Contribution update - 401(k)": "As a participant, I need
to choose a new 401(k) contribution rate in the chat and confirm it before it is submitted, so
that the change is exactly what I intended."

Related: BL-061 (contribution changes; real changes are on hold until the client decides
whether contribution changes are in scope) and step-up authentication (method still to be
decided).

## User Scenarios & Testing *(mandatory)*

Worked figures in the scenarios below use the demo payroll: annual salary $100,000 (monthly
pay $8,333.33), employer match 100% up to 5% of pay, starting contribution 5%.

### User Story 1 - Change my contribution after confirming it (Priority: P1)

A signed-in participant with access to AI planning tells the agent "change my 401(k)
contribution to 8%". The agent shows what would change: their current and new contribution
rate, and per month the change in their own contribution and in the employer match. It asks
them to reply "confirm" or "cancel", and says that nothing has changed yet. When they reply
"confirm", their (mock) contribution is updated and the agent states the result. When they
reply "cancel", nothing changes.

**Why this priority**: This is the end-to-end flow BL-037 asks for: an action that runs only
after the participant has seen exactly what will happen and agreed to it.

**Independent Test**: As one test participant, propose 8%, check the summary figures, confirm,
and check that the participant's contribution is now 8% and the agent's reply says so. Repeat
with "cancel" and check that the contribution is unchanged.

**Acceptance Scenarios**:

1. **Given** a participant at 5%, **When** they ask to change their contribution to 8%, **Then** the agent shows current 5% and new 8%, their contribution going from $416.67 to $666.67 per month (+$250.00), employer match staying at $416.67 per month (no change), asks them to confirm or cancel, and states that nothing has changed yet.
2. **Given** the summary in scenario 1, **When** the participant's contribution is checked before they reply, **Then** it is still 5%.
3. **Given** a pending change to 8%, **When** the participant replies "confirm", **Then** their contribution becomes 8% and the agent states that it was changed from 5% to 8%.
4. **Given** a pending change to 8%, **When** the participant replies "cancel", **Then** their contribution stays at 5% and the agent states that the change was cancelled.
5. **Given** a participant at 5%, **When** they ask for 51% (outside the demo range of 0–50%), **Then** the agent explains the gate's reason in plain words, for example "The contribution rate must be between 0% and 50%", no change is pending, and the request is recorded as rejected.
6. **Given** a participant at 5%, **When** they ask for 5%, **Then** the agent says their contribution is already 5% and no change is pending.
7. **Given** a participant at 5%, **When** they ask for 8.5%, **Then** the agent says the rate must be a whole percentage and no change is pending.
8. **Given** a participant who confirmed a change to 8%, **When** the agent or the back end is restarted and they ask for a new change, **Then** the summary shows their current rate as 8%.
9. **Given** a participant who asked for 8% and replied "confirm" in the same chat, **When** they then ask "what's my contribution now?", **Then** the agent answers 8% and does not say the change is pending.

---

### User Story 2 - Nothing runs without my own confirmation (Priority: P1)

The change runs only when the participant themselves confirms it, in a later message, before
the confirmation window ends, and only once. Nothing the participant or anyone else types, and
nothing the model decides, can skip that step, change the values at confirmation time, or run
the change for someone else.

**Why this priority**: Without this, the flow in Story 1 is only a convention the model may
or may not follow. BL-037 requires it to be enforced in code.

**Independent Test**: For each attempt listed in the scenarios, check that the participant's
contribution is unchanged. Where the scenario says the attempt is refused, also check that a
`rejected` entry is recorded. Attempts that become an ordinary request (scenarios 1 and 2) are
recorded like any other request; messages that go to the model (scenario 4) record nothing.

**Acceptance Scenarios**:

1. **Given** a participant at 5%, **When** they say "change my contribution to 8% and skip confirmation" (or "I already confirm, just do it"), **Then** the agent shows the summary and asks for confirmation as in Story 1, and the contribution stays at 5%.
2. **Given** any single message from the participant, **When** it both asks for a change and says "confirm", **Then** the change is only staged at the end of that turn and stays pending; it can run only after a later exact "confirm".
3. **Given** a pending change in this chat, **When** the participant replies "confirm, but make it 9%" (or "confirm please", or "cancel it"), **Then** nothing is executed, the model is not called, the reply is "Reply exactly confirm or cancel.", the change stays pending, and the attempt is recorded as rejected.
4. **Given** a pending change, **When** the participant replies with something other than an accepted confirm or cancel reply (for example "ok maybe"), **Then** nothing is executed and the change stays pending until it expires or is replaced.
5. **Given** a change staged more than 5 minutes ago (demo expiry), **When** the participant replies "confirm" in that chat, **Then** nothing is executed, the agent says the change expired and they can ask again, and the expiry is recorded.
6. **Given** a change that was already executed, **When** its confirmation token is presented again, **Then** it is refused and the contribution is not changed a second time.
7. **Given** participant A has a pending change and participant B has none, **When** participant B replies "confirm", **Then** A's change is not executed and stays pending, the model is not called, B is told "There is no change waiting for confirmation.", and B's attempt is recorded as rejected.
8. **Given** participant A's confirmation token, **When** it is presented for participant B, **Then** it is refused and neither contribution changes.
9. **Given** a participant whose chat is in education-only mode, or whose token doesn't grant AI planning, **When** they ask to change their contribution, **Then** the agent says it can't make changes right now and nothing is staged.
10. **Given** a pending change, **When** the participant's chat is in education-only mode and they reply "confirm", **Then** nothing is executed and the refusal is recorded.
11. **Given** a turn whose sign-in token is missing, expired or fails the agent runtime's own verification, **When** a change is asked for, **Then** it is refused and nothing is staged, and ordinary questions are still answered; **When** the message is "confirm" or "cancel", **Then** the model is not called, nothing is executed, and the reply is "Your sign-in has expired. Please sign in again, then reply confirm or cancel." (logged, not recorded).
17. **Given** the agent's sign-in or database settings are missing, **When** the participant sends "confirm" or "cancel", **Then** the model is not called, nothing is executed, and the reply is "Contribution changes aren't available right now." (logged, not recorded).
12. **Given** a participant has a pending change proposed in chat session 1, **When** they reply "confirm" (or "cancel") in chat session 2, **Then** nothing is executed, the model is not called, they are told "That change can only be confirmed in the chat where it was proposed.", the attempt is recorded as rejected, and the change stays pending in chat session 1 until it expires.
13. **Given** a participant asks for a valid change, **When** the model's turn ends after the staging deadline (demo default 50 seconds), **Then** nothing is staged and the participant is asked to try again.
14. **Given** a participant asks for a valid change, **When** writing the staged change fails or passes the database time limit (demo default 3 seconds), **Then** nothing is staged and the participant is asked to try again.
15. **Given** a participant with nothing pending in any chat, **When** they reply "confirm" or "cancel", **Then** nothing is executed, the model is not called, they are told "There is no change waiting for confirmation.", and the attempt is recorded as rejected.
16. **Given** two participants whose turns run at the same time, **When** each asks for a change, **Then** each turn's request is checked, staged and recorded only for that participant and that chat; neither turn can see or stage the other's request.

---

### User Story 3 - Be warned before giving up employer match (Priority: P2)

When the new rate is below the employer's match cap, the summary says how much employer match
per month the participant would miss. The participant still decides; the warning never blocks
the change.

**Why this priority**: Lowering a contribution below the match cap is the costliest mistake in
this flow, and the participant should see it in dollars before they confirm.

**Independent Test**: Propose a rate below 5% and check the warning amount; confirm and check
the change runs.

**Acceptance Scenarios**:

1. **Given** a participant at 5%, **When** they ask for 3%, **Then** the summary shows their contribution going from $416.67 to $250.00 per month (−$166.67), employer match going from $416.67 to $250.00 per month (−$166.67), and a warning that they would miss $166.67 per month of employer match.
2. **Given** the warning in scenario 1, **When** the participant replies "confirm", **Then** the change to 3% runs.
3. **Given** a participant at 5%, **When** they ask for 0%, **Then** the warning says they would miss $416.67 per month of employer match.
4. **Given** a participant at 3%, **When** they ask for 4%, **Then** the summary shows the match going up by $83.33 per month and warns that they would still miss $83.33 per month of employer match.
5. **Given** a participant at 5%, **When** they ask for 8%, **Then** no match warning is shown.

---

### User Story 4 - Every step is recorded (Priority: P2)

Each step of every action attempt is recorded with the participant's ID, the time and the
outcome, so anyone reviewing later can see what was staged, what was refused, what the
participant confirmed or cancelled, and what ran.

**Why this priority**: BL-037 requires the confirmation to be recorded. It also makes the
refusals in Story 2 checkable.

**Independent Test**: Run a staged change through to execution, a cancellation, an expiry and a
rejected request, and check that the record has one entry per step with only the permitted fields.

**Acceptance Scenarios**:

1. **Given** a request for 8% that is confirmed, **When** the record is read, **Then** it shows, in order, staged, confirmed and executed, each with the participant ID, time and outcome.
2. **Given** a request for 51%, **When** the record is read, **Then** it shows rejected with the reason, and no pending change exists for it.
3. **Given** a cancelled change and an expired change, **When** the record is read, **Then** they show cancelled and expired.
4. **Given** any record entry, **When** it is inspected, **Then** it contains no chat text, name, salary or other personal data beyond the participant ID.
5. **Given** two participants acting at the same time, **When** each reads their own record, **Then** it contains only their own entries.

---

### Edge Cases

- The participant proposes a new change while one is pending: the earlier change is cancelled (recorded as cancelled, replaced) and the new one is staged. A participant has at most one pending contribution change.
- The participant replies "confirm" or "cancel" with nothing pending: the agent says "There is no change waiting for confirmation."; the attempt is recorded as rejected.
- The model asks for a change more than once in one turn: only the last request whose check passed is staged, and each request that broke a rule is recorded as rejected.
- A message starts with "confirm" or "cancel" but isn't about the pending change (for example "cancel my last question"): it gets the fixed reply in code like any other confirm or cancel message. The participant can rephrase.
- A confirm or cancel message when actions can't run is never sent to the model. With a missing, expired or invalid token the reply is "Your sign-in has expired. Please sign in again, then reply confirm or cancel."; with missing agent sign-in or database settings, or an unreadable store, it is "Contribution changes aren't available right now." These are logged and traced, not recorded. Other messages are answered normally, with actions refused.
- Two "confirm" replies for the same change arrive at the same time (two tabs): the change runs once; the second is refused.
- The agent or the back end restarts between the proposal and "confirm": the pending change survives and can still be confirmed before it expires. The conversation itself is not remembered (session memory is BL-012).
- The participant replies "confirm" in a different chat of their own: refused with "That change can only be confirmed in the chat where it was proposed.", because a pending change can be confirmed only in the chat session where it was proposed (User Story 2, scenario 12).
- Expiry is noticed on the participant's next message in any chat: the change is recorded as expired then, and can no longer run. An exact "confirm" or "cancel" in the chat where it was staged gets the expired message, without calling the model.
- Two participants' turns run at the same time: each turn's memory (the participant, the chat and the held request) belongs to that participant's conversation in that chat only, and is cleared at the end of the turn.
- Applying the change fails (for example, the store can't be written, or the database time limit passes): nothing changes, the participant is told it didn't go through and can try again, and the step is recorded as failed (or, on a time-out, the change stays pending).
- The back end can't reach the agent and returns its mock reply: no action is proposed. "Confirm" and "cancel" also get the mock reply, because the gate runs in the agent runtime, and the pending change expires unless the agent is back and the participant confirms before then. This is an accepted change from revision 1.
- The model is slow: the change is staged only if the turn ends before the staging deadline (demo default 50 seconds), which is lower than the back end's wait for the agent (demo default 60 seconds). Otherwise nothing is staged and the participant is asked to try again. So when the back end gives up and shows its mock reply, no new change has been staged.
- The agent runtime records a gate step but the back end fails to store the reply: the gate's state and record are still correct and are the authoritative record; that turn is missing from the chat history.
- The agent runtime is missing its sign-in or database settings, or its staging deadline isn't lower than the back end's wait: actions are disabled, one start-up warning names the problem, and ordinary chat keeps working.
- The participant's current rate changed between the summary and "confirm" (not possible with demo data, but possible with a real recordkeeper): nothing runs, and they are asked to propose again so they see the new figures.
- The model claims a change was made without asking the gate: a change can only run through the gate, so nothing changed, but the false claim can reach the participant, because it is the model's own text. It is guarded by the system prompt and an evaluation case, not by code (FR-013). Whenever a change is staged, or staging fails, the gate's message replaces the model's reply.
- The participant gives the rate in words ("eight percent") or with a percent sign: the model converts it to a number (8) before asking for the change. The request tool accepts numbers only, so "8%" or "eight" passed as text is refused. The gate's checks apply to the number it receives. An evaluation case covers the conversion.
- Text inside tool output or demo data that says to skip confirmation: treated as data (spec 005 FR-008); it changes nothing.
- The demo payroll seed file is missing or invalid: no change can be staged; the agent explains that contribution changes aren't available right now.

## Requirements *(mandatory)*

### Functional Requirements

**Gate flow (generic)**

- **FR-001**: Every agent action that changes data MUST go through one gate with the steps: propose, check, stage, confirm, run, record. No action MAY run any other way.
- **FR-002**: The gate MUST be generic: each action type supplies its own rule set and summary, and other action types (account opening, funding, transfers) MUST be able to use the same flow later without changing it. Only the contribution change is built in this spec.
- **FR-003**: A request MUST be checked against its action's rules, without writing anything, when the model asks for it. A failed check MUST return the reason to the model so it can explain it in plain words, and MUST stage nothing. At the end of the turn, if the turn is within the staging deadline (FR-032), the failed request MUST be recorded as rejected with its reason (FR-025), without a pending change.
- **FR-004**: A request that passes the check is held only in that turn's memory. It MUST be staged only after the model's turn has finished, and only if the turn is within the staging deadline (FR-032). A staged change MUST hold the exact values that will run. The reply MUST then be the gate's summary, with a request to confirm or cancel and a statement that nothing has changed yet, in place of the model's text.
- **FR-005**: A change MUST run only after the participant's own explicit confirmation, recognised in code by the agent runtime before the model is called. Every message that is exactly, or starts with, an accepted confirm or cancel reply (demo defaults: "confirm", "cancel") MUST be handled in code without calling the model, including when actions can't run. The first case that applies wins:
  1. The agent's sign-in settings (issuer, audience, key set URL) or database setting are missing, so actions are disabled: "Contribution changes aren't available right now."
  2. The participant's token is missing, expired or invalid: "Your sign-in has expired. Please sign in again, then reply confirm or cancel." The log entry MUST state which case occurred (token missing, token expired or token invalid), and never contains the token.
  3. The store can't be read (a database error or time-out while looking up pending changes): "Contribution changes aren't available right now."
  4. Exact reply, and a pending, unexpired change in this chat: confirm or cancel it.
  5. Exact reply, and the change in this chat expired on this message: the gate's expired message.
  6. A pending change in this chat, but the message has more words (for example "confirm please" or "confirm, but make it 9%"): "Reply exactly confirm or cancel." Nothing runs.
  7. Nothing pending in this chat, but a pending change in another chat of the same participant: "That change can only be confirmed in the chat where it was proposed."
  8. Nothing pending: "There is no change waiting for confirmation."

  Matching ignores case, surrounding whitespace, and the punctuation marks . , ! ? ; : and quotes. "Starts with" means the first word, with those marks removed, is an accepted reply ("confirmed" and "confirmation" don't count). If the store can't be read, messages that are not confirm or cancel messages still go to the model, with actions refused. Cases 1 to 3 are logged and traced, not recorded (FR-025). Cases 6 to 8 are recorded as rejected. Every other message goes to the model, which has no way to confirm or cancel. Because a change is staged only at the end of a turn, a confirmation is always a later message. Wording such as "skip confirmation" MUST have no effect.
- **FR-006**: Confirmation MUST NOT accept new values. It runs only the staged change; a confirm reply that asks for different values runs nothing.
- **FR-007**: Confirming MUST issue a one-time confirmation token bound to the participant, the chat session and the staged change. Running the change MUST require that token. A token MUST be refused if it was already used, belongs to another participant, chat session or change, or the staged change has expired.
- **FR-008**: A staged change MUST expire if not confirmed within the expiry time (demo default 5 minutes from staging). An expired change MUST NOT run.
- **FR-009**: "Cancel" (demo default accepted reply: "cancel") MUST discard the pending change with nothing changed.
- **FR-010**: A participant MUST have at most one pending change per action type. A newly staged change replaces the pending one, which is recorded as cancelled.
- **FR-011**: The gate MUST NOT let a participant propose, confirm, cancel or run any action when their chat is in education-only mode, or when their verified token doesn't carry the claim `ai_planning` set to `true`. The gate honours the education-only flag for actions only; the agent's other behaviour under the flag is not changed by this spec.
- **FR-012**: The gate MUST have a defined step before running a change where an extra identity check, step-up authentication (method still to be decided), can be required later. In this spec that step always passes, and a test MUST show that if it refuses, nothing runs.
- **FR-013**: A change MUST be able to run only through the gate. Messages about the outcome of a gate step (staged, executed, cancelled, expired, refused, failed) MUST come from the gate's result, not be composed by the model, and MUST be added to the agent's conversation for that chat, without the demo footer (the three replies when actions can't run, FR-005 cases 1 to 3, are not added), so the model's later answers are consistent with them (after "confirm", "what's my contribution now?" answers with the new rate and doesn't say "pending"). The gate cannot stop the model from writing a false success claim in an ordinary reply when it never asked the gate for anything; that risk is guarded by the system prompt and an evaluation case, not by code.

**Identity and isolation**

- **FR-014**: The gate runs in the agent runtime (BL-037) and MUST act only for the participant identity in a sign-in token that the agent runtime has verified itself, with the same issuer, audience and keys as the back end (specs 008/009, BL-001). That identity MUST NOT come from chat text, a request field or the model.
- **FR-015**: The back end MUST forward the participant's own bearer token to the agent, unchanged and never logged. The gate MUST take the participant ID only from that verified token's subject. No participant ID is sent in any request body.
- **FR-016**: If the token is missing or fails verification, the gate MUST refuse every action (fail closed) and ordinary chat MUST keep working. This is how the POC reads BL-001: the agent still answers, but without actions. Such a refusal is logged without the token; it cannot be recorded against a participant.
- **FR-016a**: If the agent runtime is missing any of its sign-in settings (issuer, audience, key set URL) or its database setting, actions MUST be disabled and one start-up warning MUST name the missing settings. Ordinary chat keeps working.
- **FR-017**: One participant's proposals, pending changes, tokens, contribution and record MUST NOT affect or be visible to another participant. The turn's memory (the verified participant, the chat session, held and rejected requests) MUST belong to one participant and one chat only, and MUST be cleared at the end of each turn. Two participants' turns, including turns running at the same time, MUST never share it. A request without a verified token MUST run with a fresh, empty conversation that is not kept, so two such requests never share anything, even with the same session ID.

**Contribution change action**

- **FR-018**: The contribution action MUST accept a new rate only if it is a whole percentage (always; not a setting) within a configurable range (demo default 0–50% inclusive) and different from the current rate.
- **FR-019**: The summary MUST show the current and new rate and, per month: the participant's contribution before and after and the difference, and the employer match before and after and the difference. Amounts are in USD, calculated in code from monthly pay (annual salary ÷ 12). Each amount, including each difference and the warning amount, is calculated from the exact values and then rounded to 2 decimal places. A difference can therefore be one cent away from subtracting two rounded amounts (for example, at 4% the missed match is $83.33, not $416.67 − $333.33 = $83.34).
- **FR-020**: When the new rate is below the employer match cap, the summary MUST warn how much employer match per month the participant would miss compared with contributing at the cap. The warning MUST NOT block confirmation.
- **FR-021**: The gate MUST read and change contributions only through one replaceable contribution source with two operations: get the current rate, and apply a change with a confirmation token. In this spec it is backed by the demo payroll seed and the per-participant store; replacing it with Principal's systems later MUST NOT require changing the gate.
- **FR-022**: Demo payroll values MUST come from a new demo seed file: annual salary $100,000, employer match 100% up to 5% of pay, starting contribution 5%. The values are the same for every participant, and the file is never modified at runtime.
- **FR-023**: A participant's current rate MUST be the seed's starting rate until they first change it, and their own stored rate after that.

**Persistence and record**

- **FR-024**: Each participant's current contribution, pending changes and record MUST be kept in a persistent store that survives restarts of the agent and the back end. The store is the existing Postgres database; its tables are created only by the back end's migrations and written only by the agent runtime's gate. A pending change refers to its chat session row, which the back end creates before calling the agent. The gate's record is the authoritative record of gate steps: if the back end fails to store the gate's message afterwards, the gate's state and record stay correct.
- **FR-025**: Every step (rejected, staged, confirmed, cancelled, expired, executed, failed) MUST be recorded with the participant ID, time, action type, a reference to the staged change where one exists, and the outcome with its reason. "Rejected" covers three things: a request that broke a rule, recorded at the end of the turn with no pending change; a confirm or cancel refused by the gate; and the fixed replies in FR-005 cases 6 to 8. "Staged" means the gate wrote the change, not that the participant saw it. These are logged and traced but not recorded (accepted for the POC): turns without a verified participant, including the sign-in reply; turns with actions disabled or an unreadable store, including their fixed replies; turns that passed the staging deadline (including their rejected requests); and saves that failed. The record MUST NOT contain chat text or any other personal data.

**Configuration and boundaries**

- **FR-026**: All limits (rate range, expiry time, accepted confirm and cancel replies, staging deadline, database time limit, the back end's wait for the agent) MUST be settings with demo defaults. They are not Principal policy, and the settings and their defaults MUST be documented.
- **FR-027**: The shared demo portfolio data and its tests MUST NOT be changed.
- **FR-028**: There MUST be no UI changes; confirmation happens in chat text only.
- **FR-029**: The contract changes MUST be documented in the README and be additive. First, the back end's call to the agent carries the participant's bearer token in the `Authorization` header. Second, the agent's response gains an optional `source`, `gate` when the gate wrote the reply, read by the back end's agent client. Third, the history `source` gains the value `gate`, read by the shared front-end API type. Request bodies are unchanged. The back end otherwise only passes messages through: it verifies sign-in, creates the chat session, forwards the message and token, and stores the reply with its source.
- **FR-030**: Each rule above MUST have at least one passing automated test that runs without a model server or network, written before the code. This includes "skip confirmation", a slow model past the staging deadline, a failed or timed-out database write, a rejected request (reason returned to the model, recorded as rejected, no pending change), confirmation from another participant, another chat, after expiry or with extra text, each fixed reply in FR-005, two participants' turns never sharing turn memory, a reused token, a missing or invalid token with chat still working, and a decrease below the match. An automated test MUST also show that after a confirmed change the agent's conversation holds the confirmed result without "pending". The live evaluation case "what's my contribution now?" after a confirmed change needs a model server, so it is run by hand and is not part of the automated suite.
- **FR-031**: Every message written by the gate MUST end with the line "Demo data: no real account was changed." The line appears only on gate messages, never on the model's replies, and is never added to the agent's conversation.

**Timing**

- **FR-032**: A held request MUST be staged, and a rejected request recorded, only if the time since the turn started is under the staging deadline (demo default 50 seconds); otherwise nothing is staged or recorded, and a participant with a held request is asked to try again. Every database statement the gate runs MUST have a time limit (demo default 3 seconds). If staging passes the limit or fails, nothing is staged and the participant is asked to try again.
- **FR-033**: The back end's wait for the agent MUST be a setting (demo default 60 seconds, replacing the fixed 10 seconds). The agent runtime MUST read that setting from the same variable, with the same default, and MUST check at start-up that its staging deadline is lower than that wait. If it isn't, actions are disabled with a clear warning. Both the back end and the agent MUST log the `AGENT_TIMEOUT_SECONDS` value they use at start-up, and the agent MUST also log its staging deadline. For this POC both read the shared `.env`.

### Key Entities

- **Action policy**: a kind of write action the gate can run (only "contribution change" in this spec). It has its own module with its rule set, summary and executor.
- **Held request**: what the model asked for, parsed into values (for a contribution change: the new rate) and checked. It exists only in that turn's memory, until the gate stages it at the end of the turn.
- **Staged change**: a checked proposal waiting for confirmation. It belongs to one participant and the chat session where it was proposed, and holds the exact values to run, the summary shown, when it was staged and when it expires, and its status (pending, confirmed, cancelled, expired, executed, failed).
- **Confirmation token**: issued once when the participant confirms. It is bound to one participant, one chat session and one staged change, and is valid for a single run before the change expires.
- **Participant contribution**: a participant's current contribution rate. It starts from the demo seed and is updated only by an executed change.
- **Demo payroll seed**: salary, match rate, match cap and starting contribution. It is shared by all participants and read-only.
- **Record entry**: one step of one action attempt: participant ID, time, action type, staged-change reference, outcome and reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A participant can change their contribution in two messages (the request and "confirm") in under one minute.
- **SC-002**: In automated tests, 0 changes run without the participant's own confirmation, including "skip confirmation", a confirmation in the same turn as the request, a confirmation with extra text or new values, an expired confirmation, a reused token, a different participant confirming, a confirmation from a different chat session, education-only mode, a missing or invalid sign-in token and a refusing step-up check. Also, 0 changes are staged by a turn past the staging deadline or by a failed or timed-out database write.
- **SC-003**: Every summary figure in the acceptance scenarios matches to the cent.
- **SC-004**: 100% of steps in the automated tests produce exactly one record entry, and no entry contains personal data beyond the participant ID. This excludes the cases FR-025 lists as logged and traced only.
- **SC-005**: After a restart, 100% of participants' current contributions, pending changes and records are unchanged.
- **SC-006**: In a test with two participants acting at the same time, neither participant's contribution, pending change or record is affected by the other.
- **SC-007**: All existing agent, back-end and front-end tests still pass, and the shared demo portfolio and its tests are unchanged.

## Assumptions

- The gate runs in the agent runtime (BL-037) and keeps its state in the existing Postgres database, whose schema the back end owns (plan.md, research R1, R6). The back end verifies sign-in, creates the chat session, forwards the token and stores the reply. The demo payroll seed is `agent/src/wealth_agent/data/payroll.json`.
- With the agent unavailable, "confirm" and "cancel" get the back end's fallback reply and a pending change expires. This is accepted for the POC.
- Participants without AI-planning access are already refused by the back end (spec 009). The agent runtime still refuses actions unless the verified token grants AI planning, for callers that don't go through the back end.
- "Confirm" and "cancel" are the only accepted replies by default. Friendlier replies ("yes", "go ahead") are deliberately not accepted, so an ambiguous reply never runs a change. The list is a setting.
- Whole percentages only, because typical 401(k) plans use whole-percent elections. It is a fixed rule, not a setting.
- The match warning compares the new rate with the match cap, not with the current rate. This way a participant who stays below the cap after a small increase still sees what they are missing. For a decrease from the cap, both comparisons give the same amount.
- Expiry is measured from when the change is staged. Because the change runs immediately after confirmation, the token needs no separate expiry.
- A pending change can be confirmed only in the same chat session where it was proposed, which is where the participant saw the summary. The back end already sends the chat session ID with every message, after checking that the session is the participant's.
- The record is kept for the life of the demo store; no retention policy is defined for the POC.
- Taxes, contribution limits (IRS annual limits), vesting and payroll timing are ignored in the demo figures.
- Turn 2 is linked to turn 1 only through the stored pending change, looked up by the verified participant and the chat session. It does not depend on conversation memory (BL-012), which stays out of scope.

### Out of scope

- Real recordkeeper or payroll integration (BL-061; real changes are on hold until the client decides whether contribution changes are in scope).
- Step-up authentication itself (method still to be decided); only the hook in FR-012 is built.
- Any change to the agent's behaviour in education-only mode other than refusing actions.
- Any change to spec 005 (`specs/005-*`).
- Other action types (account opening, funding, transfers).
- UI confirmation buttons; confirmation is chat text only.
- End-to-end tracing (BL-014) and session memory (BL-012).

## Notes for the plan step

Carried over from the request; the design must hold as the POC evolves:

- The gate is generic (FR-002): other actions must be able to use the same propose, check, stage, confirm, run, record flow, each with its own rule set. Build only the contribution action now.
- The contribution source (FR-021) is one small interface (get current rate; apply a change with a confirmation token). Today it is backed by the demo seed and the store; later it is replaced by a call to Principal's systems without changing the gate.
- Leave a clear hook where step-up authentication (method still to be decided) will be required before execution (FR-012).
- Resolve how the agent receives the signed-in participant's ID from the back end (FR-015, FR-016). Specs 008/009 verify it in the back end today; the agent request currently carries `prompt`, `session_id` and `education_only`. Also decide how to establish trust between the back end and the agent once the agent is hosted. *Resolved in plan.md revision 3 (research R1, R2): the back end forwards the participant's token and the agent runtime verifies it itself (BL-001); no ID is sent and no service-to-service trust is added.*
- Decide how FR-005 is enforced in code (the confirm or cancel reply is recognised from the participant's own message, not from a model tool call), and how the agent knows the education-only marker (FR-011), using it for actions only. *Resolved in plan.md revision 3 (research R3, R4, R18): the agent entry point recognises an exact confirm or cancel for a pending change in this chat before the model runs; the model's one tool only checks a request, and staging happens at the end of the turn; the gate uses the `education_only` flag the back end already sends, plus the token's `ai_planning` claim.*
- Do not change `specs/005-*`; the spec 005 owner reviews its risk tier.
- Reuse existing project patterns and tests (`{ok, error}` tool results, validation in code, stub-model tests); keep changes small; no UI changes. Suggested seed file: `agent/src/wealth_agent/data/payroll.json` (*kept by plan revision 3, research R14*). Do not modify `agent/src/wealth_agent/data/portfolio.json` or its tests.
