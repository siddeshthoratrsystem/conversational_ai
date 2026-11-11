# Research: Guided tasks overlay

## R1. Overlay versus a new page

- **Decision**: An absolutely positioned panel inside `<main>`, rendered on top of the chat, with the chat left mounted underneath.
- **Rationale**: The Figma frame is "Guided tasks overlay" with a (hidden) close button. Keeping the chat mounted preserves messages, the composer draft, scroll position and pending replies (FR-009) with no extra state handling. The app has no router.
- **Alternatives considered**: Swapping `<main>` contents (loses scroll position and draft focus); adding a router and `/tasks` URL (new dependency, against Principle V).

## R2. Icons

- **Decision**: Use the path data from the supplied SVG exports in a shared `GuidedTaskIcon` component, drawn with `fill="currentColor"` and token text colours (`text-ink`, `text-danger-700` for the bell's dot). Each icon keeps its original coordinates and is framed with a per-icon `viewBox`, so no path data is hand-edited.
- **Rationale**: Exact match to the design; the theme test forbids hex colours in source, and `currentColor` keeps colours in tokens.
- **Alternatives considered**: lucide-react look-alikes (not the design); SVG files as assets (colours would be hard-coded in the files).
- **Provisional mapping** (designer to confirm): debt autopilot → refresh, refinancing → bank, compare strategies → line chart, roll old 401(k) → office building.

## R3. Missing tokens

- **Decision**: Add `color.danger-700 = #c00000` (bell dot) and `text.display-sm = 40px / 48px` (overlay heading) to `tokens.json` and regenerate.
- **Rationale**: Both values come straight from the design export, and tokens are the only allowed source of brand values (spec 007).

## R4. Inert rows and ⋯ marker

- **Decision**: Render rows as list items and the ⋯ as a decorative, `aria-hidden` icon; no buttons, no click handlers, no hover affordance.
- **Rationale**: Product owner decision; a control that does nothing would be announced to keyboard and screen-reader users as broken (FR-007).

## R5. Closing

- **Decision**: Tasks only opens (selecting it again keeps the overlay open, product owner decision); Escape closes and returns focus to the Tasks button; New chat and a History pick close it.
- **Rationale**: The design hides its close button; these cover the obvious exits without adding UI.
