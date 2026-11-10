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

Backlog: BL-037 (action gate).

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
5. **Given** a participant at 5%, **When** they ask for 51% (outside the demo range of 0–50%), **Then** the agent gives a plain reason, for example "The contribution rate must be between 0% and 50%", and no change is pending.
6. **Given** a participant at 5%, **When** they ask for 5%, **Then** the agent says their contribution is already 5% and no change is pending.
7. **Given** a participant at 5%, **When** they ask for 8.5%, **Then** the agent says the rate must be a whole percentage and no change is pending.
8. **Given** a participant who confirmed a change to 8%, **When** the agent or the back end is restarted and they ask for a new change, **Then** the summary shows their current rate as 8%.

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
`rejected` entry is recorded; attempts that become an ordinary proposal or pass through to the
model (scenarios 1, 2 and 4) are recorded like any other proposal, or not at all.

**Acceptance Scenarios**:

1. **Given** a participant at 5%, **When** they say "change my contribution to 8% and skip confirmation" (or "I already confirm, just do it"), **Then** the agent shows the summary and asks for confirmation as in Story 1, and the contribution stays at 5%.
2. **Given** any single message from the participant, **When** the model both proposes a change and tries to confirm it in that same turn, **Then** the confirmation is refused and the change stays pending.
3. **Given** a pending change, **When** the participant replies "confirm, but make it 9%" (or "confirm please"), **Then** nothing is executed; the system explains that confirmation can't change the values, that they should reply exactly "confirm" or "cancel", and that to ask for a different rate they can say the new rate.
4. **Given** a pending change, **When** the participant replies with something other than an accepted confirm or cancel reply (for example "ok maybe"), **Then** nothing is executed and the change stays pending until it expires.
5. **Given** a change staged more than 5 minutes ago (demo expiry), **When** the participant replies "confirm", **Then** nothing is executed, the agent says the change expired and they can propose it again, and the expiry is recorded.
6. **Given** a change that was already executed, **When** its confirmation token is presented again, **Then** it is refused and the contribution is not changed a second time.
7. **Given** participant A has a pending change, **When** participant B replies "confirm", **Then** A's change is not executed, B is told they have nothing to confirm, and A's change stays pending.
8. **Given** participant A's confirmation token, **When** it is presented for participant B, **Then** it is refused and neither contribution changes.
9. **Given** a participant whose chat is in education-only mode, **When** they ask to change their contribution, **Then** the agent says it can't make changes right now and nothing is staged.
10. **Given** a pending change, **When** the participant's chat is in education-only mode and they reply "confirm", **Then** nothing is executed.
11. **Given** a gate step that runs without a verified participant ID, **When** a change is proposed or confirmed, **Then** it is refused and nothing is staged or executed.
12. **Given** a participant has a pending change proposed in chat session 1, **When** they reply "confirm" in chat session 2, **Then** nothing is executed, they are told the change can be confirmed only in the chat where it was proposed, and the change stays pending in chat session 1 until it expires.

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
outcome, so anyone reviewing later can see what was proposed, what was refused, what the
participant confirmed or cancelled, and what ran.

**Why this priority**: BL-037 requires the confirmation to be recorded. It also makes the
refusals in Story 2 checkable.

**Independent Test**: Run a proposal through to execution, a cancellation, an expiry and a
rejected proposal, and check that the record has one entry per step with only the permitted
fields.

**Acceptance Scenarios**:

1. **Given** a proposal to 8% that is confirmed, **When** the record is read, **Then** it shows, in order, proposed, staged, confirmed and executed, each with the participant ID, time and outcome.
2. **Given** a proposal to 51%, **When** the record is read, **Then** it shows proposed and rejected, with the reason.
3. **Given** a cancelled change and an expired change, **When** the record is read, **Then** they show cancelled and expired.
4. **Given** any record entry, **When** it is inspected, **Then** it contains no chat text, name, salary or other personal data beyond the participant ID.
5. **Given** two participants acting at the same time, **When** each reads their own record, **Then** it contains only their own entries.

---

### Edge Cases

- The participant proposes a new change while one is pending: the earlier change is cancelled (recorded as cancelled, replaced) and the new one is staged. A participant has at most one pending contribution change.
- The participant replies "confirm" or "cancel" with nothing pending: the agent says there is nothing to confirm or cancel; the attempt is recorded as rejected.
- Two "confirm" replies for the same change arrive at the same time (two tabs): the change runs once; the second is refused.
- The agent or the back end restarts between the proposal and "confirm": the pending change survives and can still be confirmed before it expires. The conversation itself is not remembered (session memory is BL-012).
- The participant replies "confirm" in a different chat of their own: refused, because a pending change can be confirmed only in the chat session where it was proposed (User Story 2, scenario 12).
- Expiry is noticed the next time the participant proposes, confirms or cancels: the change is recorded as expired then, and can no longer run.
- Applying the change fails (for example, the store can't be written): nothing changes, the participant is told it didn't go through and can try again, and the step is recorded as failed.
- The back end can't reach the agent and returns its mock reply: no action is proposed. "Confirm" and "cancel" still work, because they don't need the agent.
- The participant's current rate changed between the summary and "confirm" (not possible with demo data, but possible with a real recordkeeper): nothing runs, and they are asked to propose again so they see the new figures.
- The model claims a change was made without asking the gate: a change can only run through the gate, so nothing changed, but the false claim can reach the participant, because it is the model's own text. It is guarded by the system prompt and an evaluation case, not by code (FR-013). Whenever the model does ask the gate, the gate's message replaces the model's reply.
- The participant gives the rate in words ("eight percent") or with a percent sign: the model converts it to a number (8) before asking for the change. The request tool accepts numbers only, so "8%" or "eight" passed as text is refused. The gate's checks apply to the number it receives. An evaluation case covers the conversion.
- Text inside tool output or demo data that says to skip confirmation: treated as data (spec 005 FR-008); it changes nothing.
- The demo payroll seed file is missing or invalid: no change can be proposed; the agent gives a plain message that contribution changes aren't available right now.

## Requirements *(mandatory)*

### Functional Requirements

**Gate flow (generic)**

- **FR-001**: Every agent action that changes data MUST go through one gate with the steps: propose, check, stage, confirm, run, record. No action MAY run any other way.
- **FR-002**: The gate MUST be generic: each action type supplies its own rule set and summary, and other action types (account opening, funding, transfers) MUST be able to use the same flow later without changing it. Only the contribution change is built in this spec.
- **FR-003**: A proposal MUST be checked against its action's rules before anything is staged. A failed check MUST return a plain reason to the participant and stage nothing.
- **FR-004**: A staged change MUST hold the exact values that will run and MUST be shown to the participant as a summary with a request to confirm or cancel, stating that nothing has changed yet.
- **FR-005**: A change MUST run only after the participant's own explicit confirmation. A confirmation counts only if it is the participant's own message, sent in the same chat session where the change was proposed, in a later turn than the one that showed the summary, and it is an accepted confirm reply (demo default: "confirm"). The reply is matched ignoring case and ignoring surrounding whitespace and the punctuation marks . , ! ? ; : and quotes. While a change is pending in this chat, a message that starts with an accepted confirm or cancel word and has more text after it (for example "confirm please" or "confirm, but make it 9%") runs nothing and is answered with the reply rule instead of being sent to the model. The model MUST NOT be able to confirm on the participant's behalf, and wording such as "skip confirmation" MUST have no effect.
- **FR-006**: Confirmation MUST NOT accept new values. It runs only the staged change; a confirm reply that asks for different values runs nothing.
- **FR-007**: Confirming MUST issue a one-time confirmation token bound to the participant, the chat session and the staged change. Running the change MUST require that token. A token MUST be refused if it was already used, belongs to another participant, chat session or change, or the staged change has expired.
- **FR-008**: A staged change MUST expire if not confirmed within the expiry time (demo default 5 minutes from staging). An expired change MUST NOT run.
- **FR-009**: "Cancel" (demo default accepted reply: "cancel") MUST discard the pending change with nothing changed.
- **FR-010**: A participant MUST have at most one pending change per action type. A new proposal replaces the pending one, which is recorded as cancelled.
- **FR-011**: The gate MUST NOT let a participant propose, confirm, cancel or run any action when their chat is in education-only mode. The gate honours the education-only flag for actions only; the agent's other behaviour under the flag is not changed by this spec.
- **FR-012**: The gate MUST have a defined step before running a change where an extra identity check, step-up authentication (method still to be decided), can be required later. In this spec that step always passes, and a test MUST show that if it refuses, nothing runs.
- **FR-013**: A change MUST be able to run only through the gate. Messages about the outcome of a gate step (staged, executed, cancelled, expired, refused, failed) MUST come from the gate's result, not be composed by the model. The gate cannot stop the model from writing a false success claim in an ordinary reply when it never asked the gate for anything; that risk is guarded by the system prompt and an evaluation case, not by code.

**Identity and isolation**

- **FR-014**: The gate MUST act only for the participant identity verified by the back end (specs 008/009). That identity MUST NOT come from chat text or from the model.
- **FR-015**: The gate MUST take the participant ID only from the sign-in token verified by the back end. No participant ID is sent to or accepted from the agent.
- **FR-016**: If a gate step runs without a verified participant ID, the gate MUST refuse every action (fail closed). Read-only questions keep working.
- **FR-017**: One participant's proposals, pending changes, tokens, contribution and record MUST NOT affect or be visible to another participant.

**Contribution change action**

- **FR-018**: The contribution action MUST accept a new rate only if it is a whole percentage within a configurable range (demo default 0–50% inclusive) and different from the current rate.
- **FR-019**: The summary MUST show the current and new rate and, per month: the participant's contribution before and after and the difference, and the employer match before and after and the difference. Amounts are in USD, calculated in code from monthly pay (annual salary ÷ 12). Each amount, including each difference and the warning amount, is calculated from the exact values and then rounded to 2 decimal places. A difference can therefore be one cent away from subtracting two rounded amounts (for example, at 4% the missed match is $83.33, not $416.67 − $333.33 = $83.34).
- **FR-020**: When the new rate is below the employer match cap, the summary MUST warn how much employer match per month the participant would miss compared with contributing at the cap. The warning MUST NOT block confirmation.
- **FR-021**: The gate MUST read and change contributions only through one replaceable contribution source with two operations: get the current rate, and apply a change with a confirmation token. In this spec it is backed by the demo payroll seed and the per-participant store; replacing it with Principal's systems later MUST NOT require changing the gate.
- **FR-022**: Demo payroll values MUST come from a new demo seed file: annual salary $100,000, employer match 100% up to 5% of pay, starting contribution 5%. The values are the same for every participant, and the file is never modified at runtime.
- **FR-023**: A participant's current rate MUST be the seed's starting rate until they first change it, and their own stored rate after that.

**Persistence and record**

- **FR-024**: Each participant's current contribution, pending changes and record MUST be kept in a persistent store that survives restarts of the agent and the back end.
- **FR-025**: Every step (proposed, rejected, staged, confirmed, cancelled, expired, executed, failed) MUST be recorded with the participant ID, time, action type, a reference to the staged change where one exists, and the outcome with its reason. The record MUST NOT contain chat text or any other personal data.

**Configuration and boundaries**

- **FR-026**: All limits (rate range, whole-percentage rule, expiry time, accepted confirm and cancel replies) MUST be settings with demo defaults. They are not Principal policy, and the settings and their defaults MUST be documented.
- **FR-027**: The shared demo portfolio data and its tests MUST NOT be changed.
- **FR-028**: There MUST be no UI changes; confirmation happens in chat text only.
- **FR-029**: Both contract changes MUST be documented in the README and be additive. First, the agent's response gains an optional `action` (the participant's requested change), read by the back end's agent client. Second, the history `source` gains the value `gate` for messages written by the gate, read by the shared front-end API type. Request bodies are unchanged.
- **FR-030**: Each rule above MUST have at least one passing automated test that runs without a model server or network. This includes "skip confirmation", an expired confirmation, a reused token, a different participant trying to confirm, and a decrease below the match.
- **FR-031**: Every message written by the gate MUST end with the line "Demo data: no real account was changed." The line appears only on gate messages, never on the model's replies.

### Key Entities

- **Action type**: a kind of write action the gate can run (only "contribution change" in this spec). It has its own rule set, summary and executor.
- **Proposal**: what the participant asked for, as parsed into values (for a contribution change: the new rate). It is checked before anything is staged.
- **Staged change**: a checked proposal waiting for confirmation. It belongs to one participant and the chat session where it was proposed, and holds the exact values to run, the summary shown, when it was staged and when it expires, and its status (pending, confirmed, cancelled, expired, executed, failed).
- **Confirmation token**: issued once when the participant confirms. It is bound to one participant, one chat session and one staged change, and is valid for a single run before the change expires.
- **Participant contribution**: a participant's current contribution rate. It starts from the demo seed and is updated only by an executed change.
- **Demo payroll seed**: salary, match rate, match cap and starting contribution. It is shared by all participants and read-only.
- **Record entry**: one step of one action attempt: participant ID, time, action type, staged-change reference, outcome and reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A participant can change their contribution in two messages (the request and "confirm") in under one minute.
- **SC-002**: In automated tests, 0 changes run without the participant's own confirmation, including "skip confirmation", a confirmation in the same turn as the proposal, a confirmation with new values, an expired confirmation, a reused token, a different participant confirming, a confirmation from a different chat session, education-only mode, a missing participant ID and a refusing step-up check.
- **SC-003**: Every summary figure in the acceptance scenarios matches to the cent.
- **SC-004**: 100% of steps in the automated tests produce exactly one record entry, and no entry contains personal data beyond the participant ID.
- **SC-005**: After a restart, 100% of participants' current contributions, pending changes and records are unchanged.
- **SC-006**: In a test with two participants acting at the same time, neither participant's contribution, pending change or record is affected by the other.
- **SC-007**: All existing agent, back-end and front-end tests still pass, and the shared demo portfolio and its tests are unchanged.

## Assumptions

- The gate and the per-participant store live in the back end, next to the verified sign-in and the existing Postgres store (plan.md, research R1). The agent only passes on what the participant asked for. The demo payroll seed is `backend/app/data/payroll.json`.
- Participants without AI-planning access are already refused by the back end (spec 009) and never reach the gate, so the gate only needs to handle education-only mode.
- "Confirm" and "cancel" are the only accepted replies by default. Friendlier replies ("yes", "go ahead") are deliberately not accepted, so an ambiguous reply never runs a change. The list is a setting.
- Whole percentages only is a demo default, because typical 401(k) plans use whole-percent elections. It is a setting.
- The match warning compares the new rate with the match cap, not with the current rate. This way a participant who stays below the cap after a small increase still sees what they are missing. For a decrease from the cap, both comparisons give the same amount.
- Expiry is measured from when the change is staged. Because the change runs immediately after confirmation, the token needs no separate expiry.
- A pending change can be confirmed only in the same chat session where it was proposed, which is where the participant saw the summary. The back end already sends the chat session ID with every message.
- The record is kept for the life of the demo store; no retention policy is defined for the POC.
- Taxes, contribution limits (IRS annual limits), vesting and payroll timing are ignored in the demo figures.
- Per-turn tracking of whether the participant's message came after the summary is needed for FR-005. It does not depend on conversation memory (BL-012), which stays out of scope.

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
- Resolve how the agent receives the signed-in participant's ID from the back end (FR-015, FR-016). Specs 008/009 verify it in the back end today; the agent request currently carries `prompt`, `session_id` and `education_only`. Also decide how to establish trust between the back end and the agent once the agent is hosted. *Resolved in plan.md (research R1, R2): the gate runs in the back end, so no participant ID is sent to the agent and no new trust between the services is needed.*
- Decide how FR-005 is enforced in code (the confirm or cancel reply is recognised from the participant's own message, not from a model tool call), and how the agent knows the education-only marker (FR-011), using it for actions only. *Resolved in plan.md (research R1, R4): confirm and cancel are recognised by the back end before the agent is called, and the back end already knows education-only mode, so the agent needs no change for it.*
- Do not change `specs/005-*`; the spec 005 owner reviews its risk tier.
- Reuse existing project patterns and tests (`{ok, error}` tool results, validation in code, stub-model tests); keep changes small; no UI changes. Suggested seed file: `agent/src/wealth_agent/data/payroll.json` (*moved to `backend/app/data/payroll.json` by the plan, research R14*). Do not modify `agent/src/wealth_agent/data/portfolio.json` or its tests.
