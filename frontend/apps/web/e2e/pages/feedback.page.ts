import type { Locator, Page } from "@playwright/test";

/** Per-reply feedback controls (spec 004): thumbs, follow-up panel, confirmation. */
export class FeedbackPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  thumb(rating: "Helpful" | "Not helpful") {
    return this.page.getByRole("button", { name: rating, exact: true });
  }

  async rate(rating: "Helpful" | "Not helpful") {
    await this.thumb(rating).click();
  }

  /** The follow-up panel flow: pick a reason, type a comment, send. */
  async submitDetails(reason: string, comment: string) {
    await this.page.getByRole("radio", { name: reason }).check();
    await this.page.getByLabel("Comment").fill(comment);
    await this.page.getByRole("button", { name: "Send feedback" }).click();
  }

  /** aria-pressed on a thumb, as the app renders saved state. */
  async isPressed(rating: "Helpful" | "Not helpful") {
    return (await this.thumb(rating).getAttribute("aria-pressed")) === "true";
  }

  thanksNote() {
    return this.page.getByText("Thanks for your feedback");
  }
}
