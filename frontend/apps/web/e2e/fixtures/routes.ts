import type { Page } from "@playwright/test";

/**
 * In-flight failure injection for E2E (framework P3): the browser-level analogue
 * of the vitest helpers.ts fake-server flags. Use to prove the UI degrades the
 * way the contract says instead of hanging or leaking.
 */

/** The request hangs briefly, then the connection dies mid-turn (offline-ish). */
export function connectionDropsMidTurn(page: Page, urlPattern: RegExp, delayMs = 250) {
  return page.route(urlPattern, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.abort("internetdisconnected");
  });
}

/** The endpoint 500s while the flow is already running. */
export function serverFails(page: Page, urlPattern: RegExp, delayMs = 0) {
  return page.route(urlPattern, async (route) => {
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.fulfill({ status: 500, body: JSON.stringify({ detail: "boom" }) });
  });
}
