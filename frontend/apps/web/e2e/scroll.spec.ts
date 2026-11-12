import { expect, test } from "@playwright/test";

import { ChatPage } from "./pages/chat.page";

// TC-I07: auto-follow keeps the latest message in view.
// The Alfred UI has no "Scroll to latest" button — ChatApp scrollIntoView({block:"end"})
// on the end anchor keeps the newest message visible (Messages.tsx still hooks `pending`).
test.describe("short viewport", () => {
  test.use({ viewport: { width: 1280, height: 400 } });

  test("latest stays visible (TC-I07)", async ({ page }) => {
    const chat = new ChatPage(page);
    await chat.openAndSignIn();

    // Fill the thread until it overflows the short viewport.
    for (let i = 1; i <= 6; i++) {
      const text = `Scroll-${i}-${"x".repeat(60)}`;
      await chat.send(text);
      await expect(chat.replyFor(text)).toBeVisible();
    }
    // Auto-follow: latest reply is on screen without manual scroll.
    await expect(chat.replyFor("Scroll-6-")).toBeVisible();
  });
});
