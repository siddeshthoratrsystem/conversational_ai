# Tasks: Guided tasks overlay

**Input**: Design documents from `/specs/010-guided-tasks-overlay/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ui.md, quickstart.md

**Tests**: Included. The project works test-first (CLAUDE.md, constitution IV): write each test, see it fail, then implement.

All paths are relative to `frontend/`.

## Phase 1: Setup

- [X] T001 Add `"danger-700": "#c00000"` to `color` and `"display-sm": { "size": "40px", "lineHeight": "48px" }` to `text` in `packages/tokens/tokens.json`, then run `npm run tokens` to regenerate `packages/tokens/generated/principal.css` and `generated/uniwind.css`

## Phase 2: Foundational

- [X] T002 Create `packages/ui/src/web/guided-task-icon.tsx`: `GuidedTaskIcon({ name, className })` renders the 56px `rounded-lg bg-info-100` tile with a 28px `aria-hidden` SVG (`fill="currentColor"`, `text-ink`) for each `GuidedTaskIconName` (`bell-alert`, `wallet`, `receipt`, `bill`, `refresh`, `pie-chart`, `line-chart`, `building`, `bank`, `people`), using the exported path data unchanged with a per-icon `viewBox`; the bell's dot uses `text-danger-700`. Export the `GuidedTaskIconName` type

## Phase 3: User Story 1 - Browse the guided tasks (P1) 🎯 MVP

**Goal**: Tasks on the rail opens the overlay with all sections and tasks.
**Independent Test**: Select Tasks; the "Guided tasks" region shows the heading, intro, 4 sections in order and 11 tasks with exact copy.

- [X] T003 [US1] Write failing tests in `apps/web/src/__tests__/GuidedTasks.test.tsx`: Tasks button enabled and named "Tasks" with `aria-expanded=false`; clicking it shows `region` "Guided tasks" with h2 "Guided tasks", the intro, h3s Budgeting/Retirement/Debt/Savings in order, list item counts 4/3/3/1 and every title and description from spec FR-004; the header and rail stay visible; Tasks has `aria-expanded=true`
- [X] T004 [US1] Update `apps/web/src/__tests__/Enhancements.test.tsx` so the "coming soon" test covers Notifications only
- [X] T005 [US1] Create `apps/web/src/chat/GuidedTasks.tsx`: `GUIDED_TASK_SECTIONS` (data-model.md; copy exactly as spec FR-004; icons per research R2) and `GuidedTasks` rendering `<section id="guided-tasks" aria-labelledby=…>` absolutely over the chat area, white, scrollable, a 758px centred column with the design spacing (pt-16; header 36/40/16 with 6px gap; list 0/40/40 with 28px between sections; section pt-2 and 24px gap; rows 20px gap; text 4px gap), heading `text-display-sm font-light tracking-[-0.5px] text-navy`, intro `text-base text-muted`, section titles `text-xl font-bold text-navy`, task titles `text-lg font-bold text-navy`, descriptions `text-base text-muted`, and an `aria-hidden` 20px `Ellipsis` icon on the right
- [X] T006 [US1] In `apps/web/src/chat/SideRail.tsx` replace the disabled Tasks button with an enabled "Tasks" button taking `tasksOpen`/`onOpenTasks`, `active`, `aria-expanded`, `aria-controls="guided-tasks"`, and a forwarded ref
- [X] T007 [US1] In `apps/web/src/chat/ChatApp.tsx` add `tasksOpen` state, pass it to `SideRail`, and render `<GuidedTasks />` inside `<main>` when open, leaving the chat mounted underneath

## Phase 4: User Story 2 - Leave the overlay (P1)

**Goal**: Every exit returns to the same conversation.
**Independent Test**: Draft text, open and close Tasks; draft and messages unchanged.

- [X] T008 [US2] Add failing tests to `apps/web/src/__tests__/GuidedTasks.test.tsx`: Tasks again keeps it open; Escape closes and focuses Tasks; New chat closes and shows the welcome; picking a History chat closes it; a typed draft and existing messages survive open/close
- [X] T009 [US2] In `apps/web/src/chat/ChatApp.tsx` close the overlay on Escape (returning focus to the Tasks button via the ref), in `newChat()`, and after a History chat loads in `openSession()`

## Phase 5: User Story 3 - Inert parts (P2)

**Goal**: Rows and ⋯ do nothing and are not presented as controls.
**Independent Test**: Click a row and a ⋯; nothing changes and no request is sent.

- [X] T010 [US3] Add tests to `apps/web/src/__tests__/GuidedTasks.test.tsx`: no `button` or `link` inside the region; clicking a row and its ⋯ sends no chat request and leaves the overlay open

## Phase 6: Polish

- [X] T011 Run `npm test` and `npm run build` in `frontend/`; fix failures (including the theme test's no-hex check)
- [X] T012 Walk through `specs/010-guided-tasks-overlay/quickstart.md` in the running app and compare with the Figma export

## Dependencies

T001 → T002 → US1 (T003–T007) → US2 (T008–T009) → US3 (T010) → T011–T012. US3 needs only US1. Tests come before their implementation in each story.

## Parallel opportunities

T003 and T004 (different test files); T005 and T006 (different files) once T002 is done.

## Implementation strategy

MVP is US1 + US2 (both P1): the overlay must open and close cleanly to ship. US3 is mostly covered by building rows without controls and adds the tests that lock it in.
