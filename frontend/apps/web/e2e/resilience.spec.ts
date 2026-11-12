import { expect, test } from "@playwright/test";

import { ChatPage } from "./pages/chat.page";
import { FeedbackPage } from "./pages/feedback.page";
import { connectionDropsMidTurn } from "./fixtures/routes";

// Resilience & safety E2E (unlocked by framework P3 failure injection).

test("connection drops mid-turn: error style, no feedback controls (TC-I06 E2E)", async ({ page }) => {
  const chat = new ChatPage(page);
  const feedback = new FeedbackPage(page);
  await chat.openAndSignIn();

  // Block the chat POST while the turn is already in flight.
  await connectionDropsMidTurn(page, new RegExp("/api/chat$"));

  await chat.send("Pipeline dies here");

  await expect(page.getByText("Something went wrong.")).toBeVisible();

  // A failed reply is never rateable and never sent to the backend twice.
  await expect(feedback.thumb("Helpful")).toHaveCount(0);
  await expect(feedback.thumb("Not helpful")).toHaveCount(0);
});

test("malicious markup renders inert (TC-J01 XSS)", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.openAndSignIn();

  // The mock server echoes user text verbatim; the renderer must escape markup.
  const payload = '"><img src=x onerror=window.__pwned=1><script>alert(1)</script>';
  await chat.send(payload);

  // The reply shows up as plain text markup, not executed HTML.
  await expect(page.getByText(/You said:/)).toBeVisible();

  // Nothing executable materialised inside rendered messages...
  await expect(page.locator(".message img, .message script, .message iframe")).toHaveCount(0);
  // ...the injected handler never ran...
  expect(await page.evaluate(() => (window as { __pwned?: unknown }).__pwned)).toBeUndefined();
  // ...and the raw payload text is present as harmless content.
  const text = await page.locator(".message").last().textContent();
  expect(text).toContain('<img src=x onerror=');
});
