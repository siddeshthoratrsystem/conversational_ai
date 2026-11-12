import type { Page } from "@playwright/test";

/** Session store access (spec 001 / framework P3). The sidebar lists only these ids. */
export const SESSION_KEY = "convai.sessionIds";

export async function storedSessionIds(page: Page): Promise<string[]> {
  return page.evaluate(() => JSON.parse(localStorage.getItem(SESSION_KEY) ?? "[]"));
}

/** Server-side read of a conversation, bypassing the UI (books-and-records check). */
export async function readHistory(page: Page, sessionId: string) {
  return page.request.get(`/api/chat/${sessionId}/history`);
}
