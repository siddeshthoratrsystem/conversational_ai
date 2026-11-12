// Spec 004: answer feedback in the chat UI.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { history, installServer, messageBox, openHistory, seed, signInAs, type Server } from "./helpers";

const KEY = "convai.sessionIds";
let server: Server;

beforeEach(() => {
  localStorage.clear();
  signInAs();
  server = installServer();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const feedbackPosts = () => server.calls.filter((c) => c.method === "POST" && c.url.endsWith("/feedback"));
const lastFeedback = () => feedbackPosts().at(-1);
const pressed = (name: string) => screen.getByRole("button", { name }).getAttribute("aria-pressed");

async function renderApp() {
  render(<App />);
  openHistory();
  await screen.findByText(/no past chats yet/i);
}

/** Send a message and wait for its reply; returns the reply's message id. */
async function chat(text: string): Promise<number> {
  fireEvent.change(messageBox(), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText(`(mock) You said: ${text}`);
  const reply = [...server.sessions.values()].flatMap((s) => s.messages).filter((m) => m.role === "assistant").at(-1)!;
  return reply.id;
}

describe("spec 004 US1: rate an answer", () => {
  it("shows unpressed Helpful / Not helpful under a reply, and none for the user's message", async () => {
    await renderApp();
    await chat("hello");
    expect(screen.getAllByRole("button", { name: "Helpful" })).toHaveLength(1);
    expect(pressed("Helpful")).toBe("false");
    expect(pressed("Not helpful")).toBe("false");
  });

  it("saves Helpful with one tap and shows it selected", async () => {
    await renderApp();
    const id = await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    expect(lastFeedback()).toMatchObject({ url: `/api/messages/${id}/feedback`, body: { rating: "up" } });
    expect(lastFeedback()!.body).toEqual({ rating: "up" });
    expect(pressed("Not helpful")).toBe("false");
  });

  it("saves Not helpful with one tap and shows it selected", async () => {
    await renderApp();
    const id = await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" }));
    await waitFor(() => expect(pressed("Not helpful")).toBe("true"));
    expect(lastFeedback()).toMatchObject({ url: `/api/messages/${id}/feedback` });
    expect(lastFeedback()!.body).toEqual({ rating: "down" });
  });

  it("shows no rating controls on the 'Something went wrong.' reply", async () => {
    await renderApp();
    const ok = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "POST" ? new Response("{}", { status: 500 }) : ok(input, init),
      ),
    );
    fireEvent.change(messageBox(), { target: { value: "fails" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Something went wrong.");
    expect(screen.queryByRole("button", { name: "Helpful" })).toBeNull();
  });

  it("lets a reopened chat's replies be rated, starting unrated", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["a"]));
    render(<App />);
    openHistory();
    fireEvent.click(await history().findByRole("button", { name: /first topic/ }));
    await screen.findByText("(mock) You said: first topic");
    const replyId = server.sessions.get("a")!.messages[1].id;
    expect(pressed("Helpful")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    expect(lastFeedback()!.url).toBe(`/api/messages/${replyId}/feedback`);
  });

  it("shows an error with Retry when saving fails, and keeps the last saved state", async () => {
    await renderApp();
    await chat("hello");
    server.failFeedback = true;
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn't save your feedback");
    expect(pressed("Helpful")).toBe("false");
    expect(pressed("Not helpful")).toBe("false");

    server.failFeedback = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    expect(screen.queryByText(/couldn't save your feedback/i)).toBeNull();
    expect(lastFeedback()!.body).toEqual({ rating: "up" });
  });

  it("disables that reply's thumbs while a save is in progress", async () => {
    await renderApp();
    await chat("hello");
    let release!: () => void;
    server.holdFeedback = new Promise<void>((r) => (release = r));
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect((screen.getByRole("button", { name: "Helpful" }) as HTMLButtonElement).disabled).toBe(true));
    expect((screen.getByRole("button", { name: "Not helpful" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" })); // ignored while saving
    await act(async () => release());
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    expect(feedbackPosts()).toHaveLength(1);
  });

  it("keeps a rating when switching to another chat and back in the same visit", async () => {
    seed(server, "b", [["other topic", "(mock) You said: other topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["b"]));
    render(<App />);
    await openHistory().findByText("other topic");
    await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));

    fireEvent.click(history().getByRole("button", { name: /other topic/ }));
    await screen.findByText("(mock) You said: other topic");
    fireEvent.click(await history().findByRole("button", { name: /hello/ }));
    await screen.findByText("(mock) You said: hello");
    expect(pressed("Helpful")).toBe("true");
  });
});

describe("spec 004 US2: say why an answer was not helpful", () => {
  async function rateDown() {
    await renderApp();
    const id = await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" }));
    await waitFor(() => expect(pressed("Not helpful")).toBe("true"));
    return id;
  }
  const comment = () => screen.getByRole("textbox", { name: "Comment" }) as HTMLTextAreaElement;

  it("offers the four reasons, a comment box and Send after Not helpful", async () => {
    await rateDown();
    const reasons = within(screen.getByRole("radiogroup", { name: "Reason" }));
    expect(reasons.getAllByRole("radio").map((r) => r.textContent)).toEqual([
      "Incorrect",
      "Unclear",
      "I wanted a person",
      "Other",
    ]);
    expect(comment()).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send feedback" })).toBeTruthy();
  });

  it("sends the chosen reason with the rating, then closes and thanks the customer", async () => {
    await rateDown();
    fireEvent.click(screen.getByRole("radio", { name: "Unclear" }));
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for your feedback");
    expect(lastFeedback()!.body).toEqual({ rating: "down", reason: "unclear" });
    expect(screen.queryByRole("radiogroup", { name: "Reason" })).toBeNull();
    expect(pressed("Not helpful")).toBe("true");
  });

  it("sends a comment exactly as typed, with the reason", async () => {
    await rateDown();
    fireEvent.click(screen.getByRole("radio", { name: "Incorrect" }));
    fireEvent.change(comment(), { target: { value: "  The limit is wrong.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for your feedback");
    expect(lastFeedback()!.body).toEqual({ rating: "down", reason: "incorrect", comment: "  The limit is wrong.  " });
  });

  it("lets a Helpful rating add a comment, with no reasons", async () => {
    await renderApp();
    await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    fireEvent.click(screen.getByRole("button", { name: "Add a comment" }));
    expect(screen.queryByRole("radiogroup", { name: "Reason" })).toBeNull();
    fireEvent.change(comment(), { target: { value: "Clear, thanks" } });
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for your feedback");
    expect(lastFeedback()!.body).toEqual({ rating: "up", comment: "Clear, thanks" });
  });

  it("does not send a whitespace-only comment", async () => {
    await rateDown();
    fireEvent.change(comment(), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for your feedback");
    expect(lastFeedback()!.body).toEqual({ rating: "down" });
  });

  it("limits the comment to 1000 characters and shows how many are left", async () => {
    await rateDown();
    expect(comment().maxLength).toBe(1000);
    expect(screen.getByText("1000 characters left")).toBeTruthy();
    fireEvent.change(comment(), { target: { value: "abcde" } });
    expect(screen.getByText("995 characters left")).toBeTruthy();
  });

  it("keeps the plain rating and sends nothing more when the follow-up is closed", async () => {
    await rateDown();
    const before = feedbackPosts().length;
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("radiogroup", { name: "Reason" })).toBeNull();
    expect(feedbackPosts()).toHaveLength(before);
    expect(pressed("Not helpful")).toBe("true");
  });

  it("keeps the follow-up open with Retry when sending it fails", async () => {
    await rateDown();
    fireEvent.click(screen.getByRole("radio", { name: "Other" }));
    server.failFeedback = true;
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn't save your feedback");
    expect(screen.getByRole("radiogroup", { name: "Reason" })).toBeTruthy();
    expect(screen.queryByText("Thanks for your feedback")).toBeNull();

    server.failFeedback = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(lastFeedback()!.body).toEqual({ rating: "down", reason: "other" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("records 'I wanted a person' as a reason only", async () => {
    await rateDown();
    const before = server.calls.length;
    fireEvent.click(screen.getByRole("radio", { name: "I wanted a person" }));
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for your feedback");
    expect(lastFeedback()!.body).toEqual({ rating: "down", reason: "wanted_a_person" });
    expect(server.calls.slice(before).map((c) => c.url)).toEqual([lastFeedback()!.url]);
  });
});

describe("spec 004 US3: change a rating", () => {
  it("switching from Not helpful to Helpful keeps the comment and drops the reason", async () => {
    await renderApp();
    await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" }));
    await waitFor(() => expect(pressed("Not helpful")).toBe("true"));
    fireEvent.click(screen.getByRole("radio", { name: "Incorrect" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Comment" }), { target: { value: "Wrong year" } });
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for your feedback");

    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    expect(lastFeedback()!.body).toEqual({ rating: "up", comment: "Wrong year" });
    expect(pressed("Not helpful")).toBe("false");
  });

  it("switching from Helpful to Not helpful replaces the rating and opens the follow-up", async () => {
    await renderApp();
    await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" }));
    await waitFor(() => expect(pressed("Not helpful")).toBe("true"));
    expect(lastFeedback()!.body).toEqual({ rating: "down" });
    expect(screen.getByRole("radiogroup", { name: "Reason" })).toBeTruthy();
  });

  it("tapping the already selected thumb sends nothing", async () => {
    await renderApp();
    await chat("hello");
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(pressed("Helpful")).toBe("true"));
    const before = feedbackPosts().length;
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    expect(feedbackPosts()).toHaveLength(before);
    expect(pressed("Helpful")).toBe("true");
  });
});

describe("comment limit boundary", () => {
  it("counts down to exactly 0 at the limit and still submits (TC-I09 tail)", async () => {
    await renderApp();
    await chat("boundary");
    fireEvent.click(screen.getByRole("button", { name: "Not helpful" }));
    const box = await screen.findByRole("textbox", { name: "Comment" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "x".repeat(1000) } });
    expect(box.value).toHaveLength(1000);
    await waitFor(() => expect(screen.getByText("0 characters left")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await screen.findByText("Thanks for your feedback");
    expect(lastFeedback()!.body).toEqual({ rating: "down", comment: "x".repeat(1000) });
  });
});
