# Implementation Plan: Landing page refresh

**Branch**: `016-landing-page-refresh` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

## Summary

Restyle the empty-chat landing page (`Welcome`) and the message box (`Composer`) to the "L4 — Search bar — C — Glow + stroke" design. Content is static data in `Welcome.tsx`; built starter buttons reuse the existing `onAsk` send path, so no new state or API.

## Technical Context

**Language/Version**: TypeScript 5, React 19, Vite web app (`frontend/apps/web`)
**Primary Dependencies**: Tailwind v4 theme from `tokens.json`; `@convai/ui` (`AiButton`, `AlfredOrb`); lucide-react icons. No new dependency.
**Storage**: N/A
**Testing**: Vitest + Testing Library; theme test forbids hex outside `tokens.json`.
**Target Platform**: Desktop and narrow browsers (existing responsive grid kept)
**Project Type**: Web frontend only
**Constraints**: Token classes only; disclaimer unchanged (spec 006); no change to send/feedback/history behaviour.

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Contract-First | Pass | No API or agent contract change. |
| II. Agent degradation | N/A | Starter prompts use the existing send path and its fallback. |
| III. Alembic | N/A | No data. |
| IV. Tests without services | Pass | Vitest with the fake backend; tests written first. |
| V. POC simplicity | Pass | Static data, existing components, one new shadow token. |

## Design

- **Tokens**: add `shadow.glow` = `0 4px 16px rgb(0 118 207 / 0.2), 0 0 48px 2px rgb(0 145 218 / 0.32)` (design's composer field shadow).
- **`Welcome.tsx`**: `STARTERS` array `{ icon, title, body, action: { label, prompt } | null }`; `null` renders a disabled "Coming soon" button. Column `max-w-265`, `gap-7`; greeting `text-5xl font-light`; intro `text-xl text-ink`; cards `p-5 gap-3 rounded-lg border-line shadow-hairline`, icon `size-10 text-accent`, title `pt-3 text-lg font-bold text-navy`, body `pt-1.5 text-sm text-muted flex-1`, button row `py-2`. Button `aria-label` = "{label}: {title}"; coming soon = "Coming soon: {title}".
- **`ChatApp.tsx`**: welcome column width `max-w-265`; aura opacity `90` on the landing page, `20` otherwise.
- **`Composer.tsx`**: form border `border-[1.5px] border-accent shadow-glow` (focus keeps the outline); disclaimer text unchanged.

## Project Structure

```text
frontend/packages/tokens/tokens.json (+ generated CSS)   shadow.glow
frontend/apps/web/src/chat/Welcome.tsx                    starter cards, copy, layout
frontend/apps/web/src/chat/ChatApp.tsx                    welcome width, aura opacity
frontend/apps/web/src/chat/Composer.tsx                   outline + glow
frontend/apps/web/src/__tests__/Enhancements.test.tsx     landing page tests
```
