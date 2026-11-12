# Feature Specification: Landing page refresh

**Feature Branch**: `016-landing-page-refresh`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "The homepage should look like the Figma frame 'L4 — Search bar — C — Glow + stroke'. Good morning, {name}: the name is the username the user signed in with. Only the landing page for now."

**Design source**: Figma *WPI Day 1.5 (P&A and P&E)*, frames "L4 — Search bar — C — Glow + stroke" and "AI / Card · Close the gap" (CSS and screenshots supplied by the product owner in chat).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A personal, design-accurate landing page (Priority: P1)

A signed-in member opens a new chat and sees the new landing page: a strong blue glow at the top, the visual, "Good morning, {name}." (time of day as today), the line "Your plan moved this week: savings are up $120, and retirement still needs attention. Where shall we start?", and four starter cards in a row.

**Why this priority**: It is the first screen every member sees.

**Independent Test**: Sign in as "alex" and check the greeting, intro line and the four cards' copy.

**Acceptance Scenarios**:

1. **Given** a member signed in as "alex", **When** an empty chat shows, **Then** the heading reads "{Good morning|Good afternoon|Good evening}, Alex." with the name highlighted.
2. **Given** the landing page, **Then** it shows the intro line and four cards, each with an icon, title, description and gradient button, with the copy in FR-003.

---

### User Story 2 - Starter cards that act, or say they will (Priority: P1)

The member clicks a starter card's button and it starts the conversation with that card's question.

**Independent Test**: Click each card's button and see its prompt sent.

**Acceptance Scenarios**:

1. **Given** the landing page, **When** the member clicks "Close the gap", **Then** "How can I close the $500K gap in my retirement savings?" is sent as their message and the landing page gives way to the conversation.
2. **Given** the landing page, **When** the member clicks "Tell me more", "Build my plan" or "Explore automations", **Then** "Where could the $3,200 in my Chase savings earn more?", "Build me a plan to pay off my debt faster." or "What could you automate for my finances?" is sent.
3. **Given** the landing page, **Then** no card's button is disabled or says "Coming soon".
4. **Given** a reply is already pending, **When** the member clicks a starter button, **Then** nothing more is sent (as today).

---

### User Story 3 - The glow-and-stroke message box (Priority: P2)

The message box has a blue 1.5px outline and a soft blue glow, keeping today's behaviour (attach "coming soon", Enter sends, Shift+Enter new line, send button).

**Independent Test**: Type and send a message; the box looks like the design and works as before.

**Acceptance Scenarios**:

1. **Given** any chat view, **Then** the message box shows the blue outline and glow from the design, and every existing message-box behaviour still works.

### Edge Cases

- **Usernames**: "alex" → "Alex"; "alex.smith@x.com" → "Alex"; a name that yields nothing → "there" (existing rule, unchanged).
- **Narrow or short windows**: the cards go 1 → 2 → 4 across with the space available and short screens tighten spacing, as today; under 760px tall the flock is drawn smaller, and under 600px it is dropped; no horizontal scrolling.
- **Conversation view**: the stronger glow is only on the landing page; once messages show, the glow returns to today's softer level so replies stay readable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The landing page MUST greet the member with the time-of-day greeting and the display name derived from the username they signed in with.
- **FR-002**: The landing page MUST show the intro line "Your plan moved this week: savings are up $120, and retirement still needs attention. Where shall we start?"
- **FR-003**: The landing page MUST show four starter cards, in this order:

  | Icon | Title | Description | Button |
  |---|---|---|---|
  | line chart | You’re $500K short of your retirement goal | Increasing your 401(k) contribution by $220 a month closes that gap by retirement. | Close the gap |
  | sprout | Your Chase savings has $3,200 earning nothing | There's likely a better place for that money to sit, want to see? | Tell me more |
  | trending down | Pay off your debt faster than you think | I'll build a personalized payoff plan that fits your monthly budget. | Build my plan |
  | lightning | Put your finances on autopilot | I can watch for overspending, send a monthly spend report, and more, without you having to ask. | Explore automations |

- **FR-004**: Every card's button MUST send its prompt (User Story 2) through the normal send path.
- **FR-005**: Each card button's accessible name MUST include the card title, so screen-reader users can tell the buttons apart.
- **FR-006**: The landing page MUST match the design's layout: a 1060px-wide centred column, 28px between its parts, 11px between cards, cards of equal height with the button at the bottom, the stronger top glow (90% opacity).
- **FR-007**: The message box MUST use the design's 1.5px blue outline and blue glow on every chat view without changing its behaviour.
- **FR-008**: The disclaimer under the message box MUST stay as today (spec 006 FR-002 requires it to say the assistant is an AI that can be wrong and is not financial advice).
- **FR-009**: The homepage MUST NOT show the left rail (product owner decision, matching the design). The rail, and the History panel with it, MUST appear as soon as a chat starts (including while the first reply is pending) and go again on New chat. The header and Sign out stay as they are.
- **FR-011**: The rail MUST follow the Figma "AI / Side rail": the Principal logo at the top (it starts a new chat, back to the homepage), labelled tabs Chat, Tasks and History, the member's initial at the bottom. The selected tab (Chat in a conversation, Tasks while Guided tasks is open, History while its panel is open) has a light blue box, and hovering any tab shows the same box. Chat returns to the conversation. Notifications is dropped (hidden in the design); History stays although the design hides it, so past chats remain reachable.
- **FR-012**: The message box's + MUST open the "Add to the conversation" menu (Figma "A0 — Attach menu": Upload from device, Take a photo, "Files stay private to your account"). A picked file MUST be checked (PDF, JPG or PNG, up to 10 MB; anything else is refused with a message) and shown in the box as in "A3 — Document attached" (name, type · size · ready, remove), with the prompt "Ask about this document…". Files MUST NOT be sent: there is no upload service yet (backlog BL-032), so the box says "Sending files is coming soon: only your message will be sent.", sends the text alone and then clears the file. Starting a new chat or opening another one also clears it.
- **FR-013**: The homepage MUST have a "Start guided tour" button under the plan line that runs the seven-step tour of Figma "Flow / Guided tour": the page dims and a ring marks (1) the brand, (2) the four cards, (3) the voice button, (4) the voice button in its listening state (flock as a ring, "Listening…", the button shows X), (5) the automations card, (6) the Guided tasks title (the Tasks page opens, with the rail), then (7) a closing callout with no ring. Each callout shows "n / 7", the design's copy, Skip tour and Next (Done on the last). Skip, Done and Escape end the tour; on steps 3–4 tapping the ringed voice button also moves on. Nothing is sent and no microphone is used: there is no voice service yet. The tour says "Alfred" where the design says "Eddie", and step 4 leaves out the design's "Microphone access was blocked" message, since the microphone is never asked for.
- **FR-010**: Starter cards MUST lift slightly on hover and when their button has keyboard focus, and stay still when the member prefers reduced motion.

## Success Criteria *(mandatory)*

- **SC-001**: Side by side with the design at 1440px, a reviewer finds no differences in copy, order, spacing or colours, apart from the items listed under Assumptions.
- **SC-002**: Each of the four starter buttons starts a conversation in one click.
- **SC-003**: All existing chat, history, feedback, sign-in and Guided tasks tests still pass.

## Assumptions

- **Card 1** follows the newer "AI / Card · Close the gap" frame (line-chart icon, button "Close the gap"); the full-page frame still shows an older version ("Increase now").
- **Prompts**: the design does not say what a button sends; the two prompts in User Story 2 are our wording, easy to change.
- **Copy as designed**: the card copy follows the product owner's latest screenshot of the design (card 2 "Your Chase savings has $3,200 earning nothing", buttons "Tell me more", "Build my plan", "Explore automations", and card 4's corrected description). The "Start guided tour" button runs the tour (FR-013).
- **Visual**: the homepage shows Alfred's murmuration, drawn as dots from the Figma "AI / Orb · Flock" (State=Murmur) data, because the "1b-ready-murmuration.png" image is not in the exports. Product owner decision: it is animated on the homepage, although the design shows a still. The dots drift and keep gathering into the Figma Idle sphere and scattering back into the Murmur cloud (a 9-second loop). It is moving from the moment the page shows and never holds still at either shape. It stays still when the member prefers reduced motion, and stops once a chat starts. The design will swap in a video later.
- **Disclaimer**: the design's "Projections aren’t guaranteed. See disclosures" is not used: it drops the AI/not-advice wording spec 006 requires and has no disclosures page to link to. It needs compliance sign-off and a link target first.
- **No rail on the homepage**: the product owner accepted that History, Tasks and Notifications are only reachable once a chat has started; after a page reload, the member sends a message before they can reopen an earlier chat or Guided tasks.
- **Header**: the design's "Principal Intelligence" header without Sign out is out of scope ("only the landing page"); today's header stays.
