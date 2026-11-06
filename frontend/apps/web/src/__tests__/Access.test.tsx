// Spec 009 US3: what customers see for each access result.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { setAuthClient } from "../auth/client";
import { installServer, messageBox, signInAs, type Server } from "./helpers";

let server: Server;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
  signInAs();
  server = installServer();
});

afterEach(() => {
  cleanup();
  setAuthClient(null);
  vi.unstubAllGlobals();
});

const DENIED = "AI planning isn't available for your account.";
const EDUCATION = "Right now Alfred can only answer general financial education questions.";
const chatPosts = () => server.calls.filter((c) => c.method === "POST" && c.url === "/api/chat");
const askButtons = () => screen.queryAllByRole("button", { name: /^Ask Alfred:/ });

describe("access to AI planning", () => {
  it("shows no notice when access is granted", async () => {
    render(<App />);
    await waitFor(() => expect(server.calls.some((c) => c.url === "/api/me")).toBe(true));
    expect(screen.queryByText(DENIED)).toBeNull();
    expect(screen.queryByText(EDUCATION)).toBeNull();
    expect(askButtons().length).toBeGreaterThan(0);
  });

  it("says plainly when access is denied, with a next step, and blocks planning questions", async () => {
    server.me = { ...server.me, access: "denied" };
    render(<App />);
    const notice = await screen.findByText(DENIED);
    expect(notice.closest("[role=status]")!.textContent).toContain("Contact Principal support for help.");
    expect(messageBox().disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Send" }).hasAttribute("disabled")).toBe(true);
    expect(askButtons()).toEqual([]);
    fireEvent.keyDown(messageBox(), { key: "Enter" });
    expect(chatPosts()).toEqual([]);
  });

  it("offers education only when the access check could not be completed", async () => {
    server.me = { ...server.me, access: "unavailable" };
    render(<App />);
    expect(await screen.findByText(EDUCATION)).toBeTruthy();
    expect(askButtons()).toEqual([]); // planning shortcuts hidden
    expect(messageBox().disabled).toBe(false);
    fireEvent.change(messageBox(), { target: { value: "What is an index fund?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("(mock) You said: What is an index fund?")).toBeTruthy();
  });

  it("switches to the denied notice when a send is refused", async () => {
    render(<App />);
    await waitFor(() => expect(server.calls.some((c) => c.url === "/api/me")).toBe(true));
    server.me = { ...server.me, access: "denied" }; // access removed after the chat opened
    fireEvent.change(messageBox(), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(DENIED)).toBeTruthy();
    expect(messageBox().disabled).toBe(true);
  });
});
