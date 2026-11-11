# Quickstart: Guided tasks overlay

## Automated

```bash
cd frontend
npm run tokens     # after editing tokens.json
npm test           # includes GuidedTasks.test.tsx and the theme test
npm run build      # type check + build
```

## Manual (desktop browser)

1. Start the app (see README "Run locally"), sign in, open http://localhost:5173.
2. Type a few words in the composer without sending. Click **Tasks** on the left rail.
   - Expect the Guided tasks overlay over the chat, header and rail still visible, Tasks highlighted.
   - Expect Budgeting (4), Retirement (3), Debt (3), Savings (1) with the copy in [contracts/ui.md](contracts/ui.md) and spec FR-004.
3. Click a task row and a ⋯ marker: nothing happens.
4. Press Escape: overlay closes, focus on Tasks, your draft is still in the composer.
5. Open Tasks again, click **New chat**: overlay closes and an empty chat shows.
6. Compare against the Figma frame at desktop width: only the Debt and Savings icon picks and the fallback font may differ.
