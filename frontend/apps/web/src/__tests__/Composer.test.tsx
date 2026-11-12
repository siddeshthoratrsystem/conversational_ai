// Spec 003, User Story 1: the message box (FR-004) and the send flow it drives.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { installServer, messageBox, openHistory, signInAs, type Server } from "./helpers";

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

const box = messageBox;
const shownMessages = () =>
  Array.from(document.querySelectorAll(".message")).map((el) => el.textContent ?? "");
const chatPosts = () => server.calls.filter((c) => c.method === "POST" && c.url === "/api/chat");

async function renderApp() {
  render(<App />);
  openHistory();
  await screen.findByText(/no past chats yet/i);
}

describe("spec 003 US1: message box", () => {
  it("is a multi-line text area", async () => {
    await renderApp();
    expect(box().tagName).toBe("TEXTAREA");
  });

  it("sends on Enter", async () => {
    await renderApp();
    fireEvent.change(box(), { target: { value: "hello" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(shownMessages()).toEqual(["hello", "(mock) You said: hello"]));
    expect(chatPosts()).toHaveLength(1);
  });

  it("does not send on Shift+Enter", async () => {
    await renderApp();
    fireEvent.change(box(), { target: { value: "line one" } });
    fireEvent.keyDown(box(), { key: "Enter", shiftKey: true });
    expect(chatPosts()).toHaveLength(0);
    expect(box().value).toBe("line one");
    expect(shownMessages()).toEqual([]);
  });

  it("sends nothing for empty or whitespace-only input", async () => {
    await renderApp();
    fireEvent.keyDown(box(), { key: "Enter" });
    fireEvent.change(box(), { target: { value: "   " } });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(chatPosts()).toHaveLength(0);
    expect(shownMessages()).toEqual([]);
  });

  it("disables Send while a reply is pending", async () => {
    await renderApp();
    let release!: () => void;
    server.holdChat = new Promise<void>((r) => (release = r));
    fireEvent.change(box(), { target: { value: "slow" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(document.querySelector(".pending")).not.toBeNull());
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);

    await act(async () => release());
    await waitFor(() => expect(document.querySelector(".pending")).toBeNull());
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows 'Something went wrong.' when sending fails", async () => {
    await renderApp();
    const ok = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "POST" ? new Response("{}", { status: 500 }) : ok(input, init),
      ),
    );
    fireEvent.change(box(), { target: { value: "will fail" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(shownMessages()).toEqual(["will fail", "Something went wrong."]));
  });
});

// TC-I04 / TC-I06 hardening (added in the scenario-expansion pass).
describe("composer hardening", () => {
  it("does not post again when Enter is pressed while a reply is pending", async () => {
    await renderApp();
    let release!: () => void;
    server.holdChat = new Promise<void>((r) => (release = r));
    fireEvent.change(box(), { target: { value: "slow" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(document.querySelector(".pending")).not.toBeNull());

    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(chatPosts()).toHaveLength(1));

    await act(async () => release());
    await waitFor(() => expect(shownMessages()).toEqual(["slow", "(mock) You said: slow"]));
    expect(chatPosts()).toHaveLength(1); // still exactly one post after the release
  });

  it("failed replies show the error style and zero feedback controls", async () => {
    await renderApp();
    const ok = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "POST" ? new Response("{}", { status: 500 }) : ok(input, init),
      ),
    );
    fireEvent.change(box(), { target: { value: "will fail" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(shownMessages()).toEqual(["will fail", "Something went wrong."]));
    expect(screen.queryByRole("button", { name: "Helpful" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Not helpful" })).toBeNull();
  });
});
