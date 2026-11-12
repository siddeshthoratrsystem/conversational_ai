import { expect, test } from "@playwright/test";

import { ChatPage } from "./pages/chat.page";

// TC-M05: prefers-reduced-motion respected (motion-reduce:animate-none on pending dots).
// We hold the chat request open with a slow route so the pending indicator stays visible,
// then compare computed animation-name with and without reduced motion.
async function pendingDotAnimation(page: import("@playwright/test").Page): Promise<string> {
  const chat = new ChatPage(page);
  await chat.openAndSignIn();
  // Hold the reply so the pending indicator stays on screen.
  await page.route(/\/api\/chat$/, async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  const send = chat.send("Hold please");
  await expect(page.locator(".pending")).toBeVisible();
  const anim = await page.locator(".pending").first().evaluate((el) => {
    const dot = el.querySelector("span span") as HTMLElement;
    return getComputedStyle(dot).animationName;
  });
  await send;
  return anim;
}

test.describe("reduced motion", () => {
  test("pending dots do not bounce under reduced motion (TC-M05)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    const anim = await pendingDotAnimation(page);
    expect(anim).toBe("none");
  });

  test("pending dots bounce without reduced motion (TC-M05 control)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    const anim = await pendingDotAnimation(page);
    expect(anim).not.toBe("none");
  });
});
