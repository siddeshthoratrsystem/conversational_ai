# Tasks: Landing page refresh

Paths relative to `frontend/`. Tests first.

## Phase 1: Setup

- [X] T001 Add `shadow.glow` to `packages/tokens/tokens.json` and run `npm run tokens`

## Phase 2: User Story 1 + 2 - Landing page and starter cards (P1)

- [X] T002 [US1] [US2] Rewrite the "welcome screen" tests in `apps/web/src/__tests__/Enhancements.test.tsx`: greeting uses the signed-in name; intro line shown; four cards with FR-003 copy in order; "Close the gap" sends "How can I close the $500K gap in my retirement savings?"; "Open Hyca" sends "How do I open a High-Yield Cash Account?"; two "Coming soon: {title}" buttons are disabled and send nothing
- [X] T003 [US1] [US2] Rewrite `apps/web/src/chat/Welcome.tsx` with the `STARTERS` data and layout from plan.md, keeping `greetingFor` and the short-screen rules
- [X] T004 [US1] In `apps/web/src/chat/ChatApp.tsx` widen the landing column to `max-w-265` and raise the aura to 90% opacity on the landing page only

## Phase 3: User Story 3 - Message box (P2)

- [X] T005 [US3] In `apps/web/src/chat/Composer.tsx` apply the 1.5px accent outline and `shadow-glow`; leave behaviour and the disclaimer unchanged

## Phase 3b: Follow-ups from review

- [X] T007 Starter cards lift on hover and keyboard focus, not with reduced motion, in `apps/web/src/chat/Welcome.tsx`
- [X] T008 Hide the rail and History panel on the homepage in `apps/web/src/chat/ChatApp.tsx`; add `startChat()` to `apps/web/src/__tests__/helpers.ts`; update the tests that reach History or Tasks from a fresh page and add a rail-visibility test
- [X] T009 Rebuild `apps/web/src/chat/SideRail.tsx` to the "AI / Side rail" design (logo = New chat, labelled Chat / Tasks / History, avatar, hover box); move the History panel to the wider rail in `ChatApp.tsx`; replace the Notifications test with rail tests
- [X] T010 Replace the orb above the greeting with the Figma Flock murmuration in `apps/web/src/chat/Flock.tsx` (dot data from the design, colour token `flock`), with a test
- [X] T011 Animate the Flock in `apps/web/src/chat/Flock.tsx` (drift; cloud ↔ sphere loop; still with reduced motion; stops on leaving the homepage), with tests
- [X] T012 Attach screens in `apps/web/src/chat/Attach.tsx` and `Composer.tsx` (menu, file checks, attached card, nothing uploaded), tests in `apps/web/src/__tests__/Attach.test.tsx`
- [X] T013 Guided tour in `apps/web/src/chat/Tour.tsx` (scrim and ring, callouts, listening state in `Flock.tsx` and `Composer.tsx`, Guided tasks on step 6), token `shadow-spotlight`, tests in `apps/web/src/__tests__/Tour.test.tsx`

## Phase 4: Polish

- [X] T006 Run `npm test` and `npm run build`; check the page in the browser against the design screenshot
