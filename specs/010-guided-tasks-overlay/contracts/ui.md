# UI contract: Guided tasks overlay

What tests and assistive technology can rely on.

## Rail button

- `button` named **"Tasks"**, enabled, `aria-expanded` true/false, `aria-controls="guided-tasks"`.
- Shows the selected style while the overlay is open (same as History).
- Notifications stays `button` "Notifications (coming soon)", disabled.

## Overlay

- `region` named **"Guided tasks"** (`id="guided-tasks"`), inside the chat area; header and rail stay visible.
- Heading level 2 "Guided tasks", then the intro paragraph.
- One heading level 3 per section, in order: Budgeting, Retirement, Debt, Savings.
- Each section's tasks are a `list` of `listitem`s; each item contains the task title and description text. No buttons or links inside the overlay.
- Icons and the ⋯ marker are `aria-hidden`.

## Closing

| Action | Result |
|---|---|
| Tasks button again | Overlay stays open |
| Escape (overlay open) | Overlay closes, focus on Tasks button |
| New chat | Overlay closes, empty chat |
| Pick a chat in History | Overlay closes once the chat has loaded |

The chat log, composer draft and pending replies are unchanged by opening or closing the overlay.
