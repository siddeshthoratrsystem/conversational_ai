import { expect, test } from "@playwright/test";

import { ChatPage } from "./pages/chat.page";
import { SidebarPage } from "./pages/sidebar.page";

// TC-M02 (RTM-042): mobile viewport 375px — history overlay + backdrop, chat functional.
// On narrow screens the history panel is an overlay with a `.backdrop` behind it
// (ChatApp.tsx test hooks: `layout`/`open`, `backdrop`, md breakpoint 768px).
test.describe("mobile 375px", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("history overlay + backdrop, chat stays functional (TC-M02)", async ({ page }) => {
    const chat = new ChatPage(page);
    const sidebar = new SidebarPage(page);
    await chat.openAndSignIn();

    // Given: narrow viewport, history closed
    await expect(sidebar.historyButton).toBeVisible();
    await expect(page.locator(".layout")).not.toHaveClass(/open/);
    await expect(page.locator(".backdrop")).toHaveCount(0);

    // When: open history
    await sidebar.historyButton.click();
    await expect(page.locator(".layout")).toHaveClass(/open/);
    await expect(sidebar.historyButton).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator(".backdrop")).toBeVisible();
    await expect(sidebar.historyPanel).toBeVisible();

    // When: tap outside closes it (dispatch on the backdrop itself -- hit-testing the
    // narrow overlay is fragile across browsers; the click handler is what we need).
    await page.locator(".backdrop").dispatchEvent("click");
    await expect(page.locator(".layout")).not.toHaveClass(/open/);
    await expect(sidebar.historyButton).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator(".backdrop")).toHaveCount(0);

    // Seed a session so the history has something to select
    const marker = `Mobile-${Date.now()}`;
    await chat.send(marker);
    await expect(chat.replyFor(marker)).toBeVisible();

    // When: reopen history and select the session
    await sidebar.historyButton.click();
    await expect(sidebar.historyPanel).toBeVisible();
    await sidebar.openSession(marker);
    // Then: selection closes the overlay (isNarrow) and the chat still renders
    await expect(page.locator(".layout")).not.toHaveClass(/open/);
    await expect(chat.replyFor(marker)).toBeVisible();

    // And: chat functional — composer accepts a second message at 375px
    await chat.send(`${marker}-2`);
    await expect(chat.replyFor(`${marker}-2`)).toBeVisible();
  });
});
