# Implementation Plan: Guided tasks overlay

**Branch**: `010-guided-tasks-overlay` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-guided-tasks-overlay/spec.md`

## Summary

Enable the left rail's Tasks button so it opens a static "Guided tasks" overlay over the chat area (backlog BL-042, first slice). The overlay lists 11 tasks in 4 sections with the design's own icons, inert rows and an inert ⋯ marker. It is web-only and has no backend change. The chat stays mounted underneath, so closing the overlay returns the member to exactly where they were.

## Technical Context

**Language/Version**: TypeScript 5, React 19 (Vite web app in `frontend/apps/web`)

**Primary Dependencies**: Tailwind v4 theme generated from `frontend/packages/tokens/tokens.json`; `@convai/ui` shared components. No new runtime dependency.

**Storage**: N/A (static content in the web app)

**Testing**: Vitest + Testing Library (`npm test` in `frontend/`); the existing theme test keeps hex colours out of source files.

**Target Platform**: Desktop browsers (web app only; mobile out of scope)

**Project Type**: Web application (frontend only for this feature)

**Performance Goals**: Overlay opens without a network request; renders 11 static rows.

**Constraints**: Token classes only (no hex in source; a test enforces it); keep chat state while the overlay is open; no new routes.

**Scale/Scope**: 1 new screen component, 1 shared icon component, 2 new tokens, edits to `SideRail` and `ChatApp`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Contract-First Interfaces | Pass | No change to frontend ↔ backend or backend ↔ agent contracts. README contracts unchanged. |
| II. Graceful Agent Degradation | N/A | No agent call. |
| III. Persistence Through Alembic Only | N/A | No schema or stored data. |
| IV. Tests Run Without External Services | Pass | Vitest with the existing fake backend; every acceptance scenario gets a test (tests first). |
| V. POC Simplicity | Pass | Static data in the web app, local React state, no router, no new dependency. |

Post-design re-check: still passes; the design adds only components and two tokens.

## Project Structure

### Documentation (this feature)

```text
specs/010-guided-tasks-overlay/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/ui.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
frontend/
├── packages/tokens/
│   ├── tokens.json                      # + color "danger-700" (#c00000), text "display-sm" (40/48)
│   └── generated/principal.css          # regenerated with `npm run tokens`
├── packages/ui/src/web/
│   └── guided-task-icon.tsx             # NEW: design icons in the 56px light-blue tile
└── apps/web/src/
    ├── chat/
    │   ├── GuidedTasks.tsx              # NEW: overlay + GUIDED_TASK_SECTIONS data
    │   ├── SideRail.tsx                 # Tasks button enabled, opens the overlay, shows selected
    │   └── ChatApp.tsx                  # tasksOpen state, Escape, close on New chat / History pick
    └── __tests__/
        ├── GuidedTasks.test.tsx         # NEW
        └── Enhancements.test.tsx        # "coming soon" test now covers Notifications only
```

**Structure Decision**: Frontend-only change inside the existing workspace. The icon component lives in `@convai/ui` because the design reuses it in the task start and finish messages later; the overlay and its content live with the other chat screens in `apps/web/src/chat/`.

## Complexity Tracking

No constitution violations.
