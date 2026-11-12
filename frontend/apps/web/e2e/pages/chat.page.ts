import type { Locator, Page } from "@playwright/test";

/** The chat surface (Alfred): composer, send button and the reply bubbles (spec 003). */
export class ChatPage {
  readonly page: Page;
  readonly composer: Locator;
  readonly sendButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.composer = page.getByRole("textbox", { name: "Message Alfred" });
    this.sendButton = page.getByRole("button", { name: "Send", exact: true });
  }

  /** Open the app (lands on the sign-in page) and sign in (spec 008: any user works). */
  async openAndSignIn(username = "e2e.user@example.com", password = "secret") {
    await this.page.goto("/");
    await this.page.getByLabel("Username").fill(username);
    await this.page.getByLabel("Password").fill(password);
    await this.page.getByRole("button", { name: "Sign in" }).click();
    await this.sendButton.waitFor();
  }

  /** A suggestion card on the welcome screen (Welcome.tsx SUGGESTIONS). */
  suggestion(text: string) {
    return this.page.getByRole("button", { name: `Ask Alfred: ${text}` });
  }

  async clickSuggestion(text: string) {
    await this.suggestion(text).click();
  }

  async send(text: string) {
    await this.composer.fill(text);
    await this.sendButton.click();
  }

  /** The mock reply bubble for a given message (backend echo format). */
  replyFor(text: string) {
    return this.page.getByText(new RegExp(`You said: ${text}`));
  }
}
