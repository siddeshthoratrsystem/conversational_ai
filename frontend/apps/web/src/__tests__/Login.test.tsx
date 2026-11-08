// Spec 009 US1: the sign-in prompt, signing in and out (contracts/web-auth.md "Screens").
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { setAuthClient } from "../auth/client";
import { installFakeAuth } from "./fakeAuth";
import { installServer, messageBox, signInAs, type Server } from "./helpers";

let server: Server;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
  server = installServer();
});

afterEach(() => {
  cleanup();
  setAuthClient(null);
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const prompt = () => screen.findByRole("heading", { level: 1, name: "Sign in to Alfred" });

describe("signed out", () => {
  it("shows only the sign-in prompt: no chat, history or message box", async () => {
    installFakeAuth();
    render(<App />);
    await prompt();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Message Alfred" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Past chats" })).toBeNull();
    expect(screen.queryByLabelText("Username")).toBeNull(); // the demo fields are gone
    expect(server.calls.filter((c) => c.url.startsWith("/api/"))).toEqual([]);
  });

  it("shows a status while checking for an existing sign-in", () => {
    installFakeAuth();
    render(<App />);
    expect(screen.getByRole("status").textContent).toBe("Signing in…");
  });

  it("goes to the sign-in service on Sign in", async () => {
    const auth = installFakeAuth();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(auth.calls).toContain("signInRedirect");
  });
});

describe("signing in", () => {
  it("signs in silently on load when the sign-in service still has a session", async () => {
    const auth = installFakeAuth({ providerSession: true });
    render(<App />);
    expect(await screen.findByRole("textbox", { name: "Message Alfred" })).toBeTruthy();
    expect(auth.calls).toEqual(["signInSilent"]);
  });

  it("finishes the sign-in on the callback page and returns to /", async () => {
    const auth = installFakeAuth();
    window.history.replaceState(null, "", "/auth/callback?code=abc&state=xyz");
    render(<App />);
    expect(await screen.findByRole("textbox", { name: "Message Alfred" })).toBeTruthy();
    expect(auth.calls).toEqual(["handleCallback"]);
    expect(window.location.pathname + window.location.search).toBe("/");
  });

  it("says so, with Try again, when the sign-in did not complete", async () => {
    const auth = installFakeAuth();
    auth.callbackFails = true;
    window.history.replaceState(null, "", "/auth/callback?error=access_denied");
    render(<App />);
    await prompt();
    expect(screen.getByRole("alert").textContent).toContain("Sign-in didn't complete.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(auth.calls).toContain("signInRedirect");
    expect(window.location.pathname).toBe("/");
  });

  it("says so, with Try again, when the sign-in service can't be reached", async () => {
    const auth = installFakeAuth({ unreachable: true });
    render(<App />);
    await prompt();
    expect(screen.getByRole("alert").textContent).toContain("We can't reach the sign-in service right now.");
    auth.unreachable = false;
    auth.providerSession = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("textbox", { name: "Message Alfred" })).toBeTruthy();
  });
});

describe("signed in", () => {
  it("shows the name from the sign-in service", async () => {
    signInAs("jane");
    render(<App />);
    expect(within(screen.getByRole("banner")).getByText("Jane")).toBeTruthy();
  });

  it("sends the token with every API call", async () => {
    signInAs();
    render(<App />);
    await screen.findByRole("textbox", { name: "Message Alfred" });
    await waitFor(() => expect(server.authHeaders.length).toBeGreaterThan(0));
    expect(server.authHeaders.every((h) => h === "Bearer token-0")).toBe(true);
  });

  it("signs out at the sign-in service and shows the prompt, keeping this browser's chat list", async () => {
    const auth = signInAs("jane");
    localStorage.setItem("convai.sessionIds", JSON.stringify(["a"]));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await prompt();
    expect(auth.calls).toContain("signOut");
    expect(messageBoxGone()).toBe(true);
    expect(localStorage.getItem("convai.sessionIds")).toBe(JSON.stringify(["a"]));
  });

  it("keeps tokens out of browser storage", async () => {
    localStorage.setItem("convai.user", JSON.stringify({ username: "old", token: "old-demo-token" }));
    signInAs();
    render(<App />);
    await screen.findByRole("textbox", { name: "Message Alfred" });
    const stored = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });
    expect(stored).not.toContain("token-0");
    expect(stored).not.toContain("old-demo-token"); // spec 008's demo entry is removed
  });
});

function messageBoxGone() {
  return screen.queryByRole("textbox", { name: "Message Alfred" }) === null;
}
