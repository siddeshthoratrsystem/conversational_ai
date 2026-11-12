import type { Locator, Page } from "@playwright/test";

/**
 * History panel (spec 001, Alfred): the rail's History button opens
 * `nav[aria-label="Past chats"]`; on narrow screens it is an overlay.
 */
export class SidebarPage {
  readonly page: Page;
  readonly historyButton: Locator;
  readonly historyPanel: Locator;

  constructor(page: Page) {
    this.page = page;
    this.historyButton = page.getByRole("button", { name: "History", exact: true });
    this.historyPanel = page.getByRole("navigation", { name: "Past chats" });
  }

  /** Open the history panel (it starts closed). */
  async openHistory() {
    if ((await this.historyPanel.count()) === 0) {
      await this.historyButton.click();
    }
    await this.historyPanel.waitFor();
  }

  session(title: string) {
    return this.historyPanel.getByRole("button", { name: new RegExp(title) });
  }

  async openSession(title: string) {
    await this.openHistory();
    await this.session(title).click();
  }

  emptyState() {
    return this.historyPanel.getByText("No past chats yet.");
  }
}
