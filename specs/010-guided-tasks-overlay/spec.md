# Feature Specification: Guided tasks overlay

**Feature Branch**: `010-guided-tasks-overlay`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Evo Guided tasks overlay (backlog BL-042, web only). Clicking the Tasks button on the left icon rail opens a Guided tasks overlay over the chat area, matching the Figma frame 'Evo / Guided tasks overlay'. The ⋯ icon is shown without functionality, tapping a task does nothing for now, desktop layout only."

**Backlog**: BL-042 Tasks and automations page (first slice: the ideas list only, no active tasks or automations).

**Design source**: Figma file *WPI Day 1.5 (P&A and P&E)*, frame "Evo / Guided tasks overlay" (node `10655:13343`). The exported CSS and screenshots are in the repo-root file `Evo  Guided tasks overlay.docx`, because the team has no Figma edit access and the Figma MCP server refuses read calls without it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse the guided tasks (Priority: P1)

A signed-in member is in the web chat and wants to see what Alfred can take them through. They select **Tasks** on the left icon rail. The chat area is replaced by the **Guided tasks** overlay: a heading, a one-line intro, and the guided tasks grouped into Budgeting, Retirement, Debt and Savings. Each task shows an icon, a title, a one-line description and a ⋯ marker, as in the design.

**Why this priority**: This is the whole feature. Today the Tasks button is disabled and marked "coming soon"; this makes it lead somewhere and shows members the range of guided help ahead of the journeys being built.

**Independent Test**: Sign in, select Tasks, and check that the overlay shows the heading, the intro, all four sections in order and all 11 tasks with their exact copy.

**Acceptance Scenarios**:

1. **Given** a signed-in member on the chat screen, **When** they look at the left rail, **Then** the Tasks button is enabled and no longer says "coming soon".
2. **Given** the chat screen, **When** the member selects Tasks, **Then** the Guided tasks overlay covers the chat area, with the header and the left rail still visible.
3. **Given** the overlay is open, **Then** it shows the heading "Guided tasks", the intro "Guided tasks I can take you through, start to finish. Pick one and I’ll do the heavy lifting.", and the sections Budgeting, Retirement, Debt and Savings in that order, each with the tasks and copy listed in FR-004.
4. **Given** the overlay is open, **Then** each task row shows an icon in a light blue rounded tile, the task title, its description and a ⋯ marker on the right.
5. **Given** the overlay is open, **When** the content is taller than the window, **Then** the member can scroll the overlay to reach the last task.

---

### User Story 2 - Leave the overlay and return to the chat (Priority: P1)

The member has looked at the guided tasks and wants to get back to the conversation they were having.

**Why this priority**: Without a way back, opening Tasks would strand the member and lose their place. It is part of the minimum usable slice.

**Independent Test**: Start a chat, open Tasks, close it with Escape, and check that the same conversation, typed draft and scroll position are still there.

**Acceptance Scenarios**:

1. **Given** the overlay is open, **When** the member selects Tasks again, **Then** the overlay stays open (Tasks only opens it).
2. **Given** the overlay is open, **When** the member presses Escape, **Then** the overlay closes and focus returns to the Tasks button.
3. **Given** the overlay is open, **When** the member selects New chat, **Then** the overlay closes and a new, empty chat shows (New chat behaves as it does today).
4. **Given** a conversation with messages and a half-typed message in the composer, **When** the member opens and then closes the overlay, **Then** the messages and the draft are unchanged.
5. **Given** the overlay is open, **When** the member opens History and picks a past chat, **Then** the overlay closes and that chat shows.

---

### User Story 3 - Not-yet-built parts do nothing, without looking broken (Priority: P2)

Starting a task and the ⋯ menu are not built yet. The product owner wants them visible as designed, but inert.

**Why this priority**: The design should read complete for demos, but nothing should pretend to work.

**Independent Test**: Open the overlay, click a task row and a ⋯ marker, and check that nothing changes and nothing is sent.

**Acceptance Scenarios**:

1. **Given** the overlay is open, **When** the member clicks or taps a task row, **Then** nothing happens: no chat message is sent, no navigation, and the overlay stays open.
2. **Given** the overlay is open, **When** the member clicks a ⋯ marker, **Then** nothing happens and no menu opens.
3. **Given** a keyboard or screen-reader user in the overlay, **When** they move through it, **Then** task rows and ⋯ markers are not presented as buttons or links, so there are no controls that do nothing.

---

### Edge Cases

- **Reply arrives while the overlay is open**: a reply to a message sent before opening the overlay is added to that chat as normal and is there when the overlay closes.
- **Window narrower than the design column**: there is no mobile design in this slice. On narrow windows the column narrows to fit and text wraps, with no horizontal scrolling; it is not tuned further.
- **History panel open when Tasks is selected**: the History panel stays open beside the overlay; the overlay covers only the chat area.
- **Signed-out member**: the overlay is reachable only from the chat screen, which already requires sign-in; nothing changes for signed-out visitors.
- **Education-only or not-entitled member (spec 009)**: the overlay is static information and shows the same to everyone; it starts nothing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Tasks button on the left rail MUST be enabled, labelled "Tasks" (without "coming soon"), and MUST show as selected while the overlay is open, the same way History shows as selected.
- **FR-002**: Selecting Tasks MUST open the Guided tasks overlay over the chat area; selecting it again while the overlay is open MUST leave it open (product owner decision). The header and left rail MUST stay visible and usable.
- **FR-003**: The overlay MUST show the heading "Guided tasks" and the intro "Guided tasks I can take you through, start to finish. Pick one and I’ll do the heavy lifting."
- **FR-004**: The overlay MUST show these sections and tasks, in this order, with this exact copy:

  | Section | Task title | Description |
  |---|---|---|
  | Budgeting | Get a heads-up before you overspend | A standing alert tied to your category targets. |
  | Budgeting | Catch a cash shortfall before it happens | Forecasting your balance against what's coming. |
  | Budgeting | Get a monthly spending report, automatically | A recurring readout, no need to ask. |
  | Budgeting | Find out if you're overpaying on your bills | A standing check against current offers. |
  | Retirement | Automatically raise your 401(k) contribution every year | Set a rule, like raising it 1% every January or whenever you get a raise, up to a cap you choose. |
  | Retirement | Make sure your investments still match your risk tolerance | A standing check across your retirement and taxable accounts. |
  | Retirement | Run what-if scenarios on your retirement plan | Ask things like “what if I retire at 62 and move somewhere cheaper. |
  | Debt | Put your debt payoff on autopilot | Pick avalanche, snowball, or a custom strategy. |
  | Debt | Get notified when refinancing could save you money | A standing watch on rates and offers against your profile. |
  | Debt | Compare debt payoff strategies side by side | See total interest, your debt-free date, and what extra payments change. |
  | Savings | Roll an old 401(k) into one place | Tell me where your old plan is and I’ll handle the paperwork and the call to your former provider. |

- **FR-005**: Each task row MUST show, left to right: an icon in a light blue rounded square tile, the title above the description, and a ⋯ marker aligned to the top right. Icons MUST be the design's own drawings (the overlay export and the "AI / Guided task icon" set): bell with a red dot, wallet, receipt and bill for Budgeting; refresh arrows, pie chart and line chart for Retirement, as designed. The Debt and Savings icons are not shown in the design, so they are provisional picks from the same icon set (see Assumptions).
- **FR-006**: The overlay MUST match the design's desktop layout: a centred column of the design's width on a white background, and the design's type styles, colours, spacing and tile size (see the design source).
- **FR-007**: Task rows and ⋯ markers MUST do nothing when clicked or tapped, and MUST NOT be exposed to keyboard or assistive technology as interactive controls.
- **FR-008**: The overlay MUST close when the member presses Escape (returning focus to the Tasks button), selects New chat, or opens a chat from History.
- **FR-009**: Opening and closing the overlay MUST NOT change the current conversation, the composer draft, pending replies or the History panel's contents.
- **FR-010**: The overlay MUST be exposed to assistive technology as a labelled region named "Guided tasks", with "Guided tasks" as its main heading, each section name as a subheading, and each section's tasks as a list.
- **FR-011**: The Notifications button MUST stay disabled and marked "coming soon", and New chat and History MUST keep working as today.
- **FR-012**: The task list MUST be fixed content in the web app; this feature MUST NOT add or change any backend endpoint or stored data.

### Key Entities

- **Guided task section**: a named group of guided tasks (Budgeting, Retirement, Debt, Savings), shown in a fixed order.
- **Guided task**: one entry in a section, with a title, a one-line description and an icon. It has no action yet.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From the chat screen, a member reaches the full guided tasks list in one click or tap.
- **SC-002**: All 11 tasks in 4 sections appear with copy that matches the design word for word.
- **SC-003**: A member returns to their conversation in one action (Escape, New chat or a History pick), with 100% of their messages and draft intact.
- **SC-004**: Clicking any task row or ⋯ marker causes zero chat messages and zero visible changes.
- **SC-005**: Side by side with the design at the design's desktop width, a reviewer finds no differences in copy, order, colours or spacing, apart from the icon and font substitutions listed under Assumptions.
- **SC-006**: The overlay passes the same automated accessibility checks as the rest of the chat screen, and every heading and list is announced correctly by a screen reader.

## Assumptions

- **Icons**: the product owner supplied SVG exports of the overlay (first seven tasks) and of the "AI / Guided task icon" set (line chart, refresh, pie chart, office building, bank, wallet, people). The seven designed tasks use their exported icons. The Debt and Savings icons are not in the exports, so they are provisional picks from the set for the designer to confirm: "Put your debt payoff on autopilot" → refresh, "Get notified when refinancing could save you money" → bank, "Compare debt payoff strategies side by side" → line chart, "Roll an old 401(k) into one place" → office building.
- **Font**: the design uses FS Elliot Pro (licensed); the app keeps its existing fallback font, as elsewhere.
- **Overlay, not page**: the Figma frame is named an overlay and has a hidden close button, so this is built as an overlay over the chat area with no close button and no new URL. Escape, New chat or a History pick closes it; selecting Tasks again keeps it open.
- **Copy as designed**: the what-if description is missing its closing quote and question mark in the design. It is used as designed and flagged to the designer; a corrected string is a one-line change.
- **Desktop only**: no mobile layout in this slice (product owner decision); the mobile app is out of scope.
- **Not built in this slice** (product owner decision): starting a task, the ⋯ menu, active tasks and automations, and any personalisation of the list.
- **Static content**: the list is the same for every member and comes from the web app itself, so it needs no backend, agent or contract change.
