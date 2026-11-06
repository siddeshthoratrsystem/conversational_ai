// Spec 009 US2: idle warning, sign-out after inactivity, and returning to the same chat.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { setAuthClient } from "../auth/client";
import { installServer, messageBox, openHistory, seed, signInAs, type Server } from "./helpers";
import type { FakeAuth } from "./fakeAuth";

const MIN = 60_000;
let server: Server;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
  server = installServer();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  setAuthClient(null);
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function useClock() {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
}

async function idle(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

/** Let pending fetches and renders finish while the fake clock stands still. */
async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

const boxValue = (box: HTMLElement, value: string) =>
  waitFor(() => expect((box as HTMLTextAreaElement).value).toBe(value));

const dialog = () => screen.queryByRole("dialog", { name: "Are you still there?" });

/** Come back from the sign-in service: a fresh page load on the callback URL. */
async function returnFromSignIn(auth: FakeAuth) {
  vi.useRealTimers();
  cleanup();
  setAuthClient(auth);
  window.history.replaceState(null, "", "/auth/callback?code=abc&state=xyz");
  render(<App />);
  return screen.findByRole("textbox", { name: "Message Alfred" });
}

describe("idle warning", () => {
  it("warns 2 minutes before the 15-minute timeout, with a countdown", async () => {
    useClock();
    signInAs();
    render(<App />);
    await idle(13 * MIN - 1000);
    expect(dialog()).toBeNull();
    await idle(1000);
    const d = dialog()!;
    expect(d).toBeTruthy();
    expect(d.textContent).toContain("You'll be signed out in 2:00.");
    expect(d.contains(document.activeElement)).toBe(true);
    await idle(30_000);
    expect(d.textContent).toContain("You'll be signed out in 1:30.");
  });

  it("restarts the timer on activity", async () => {
    useClock();
    signInAs();
    render(<App />);
    for (const type of ["keydown", "pointerdown", "touchstart", "focusin"]) {
      await idle(10 * MIN);
      fireEvent(window, new Event(type));
    }
    await idle(10 * MIN);
    expect(dialog()).toBeNull();
  });

  it("stays signed in from the dialog, by button or Escape", async () => {
    useClock();
    signInAs();
    render(<App />);
    await idle(13 * MIN);
    fireEvent.click(within(dialog()!).getByRole("button", { name: "Stay signed in" }));
    expect(dialog()).toBeNull();
    await idle(13 * MIN);
    fireEvent.keyDown(dialog()!, { key: "Escape" });
    expect(dialog()).toBeNull();
    await idle(12 * MIN);
    expect(messageBox()).toBeTruthy();
  });

  it("signs out from the dialog like the header button", async () => {
    useClock();
    const auth = signInAs();
    render(<App />);
    await idle(13 * MIN);
    fireEvent.click(within(dialog()!).getByRole("button", { name: "Sign out" }));
    expect(auth.calls).toContain("signOut");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Sign in to Alfred");
  });

  it("signs out after 15 minutes, clears the screen and says why", async () => {
    useClock();
    const auth = signInAs();
    render(<App />);
    fireEvent.change(messageBox(), { target: { value: "half-typed question" } });
    await idle(15 * MIN);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Sign in to Alfred");
    expect(screen.getByRole("status").textContent).toBe("You were signed out after 15 minutes of inactivity.");
    expect(screen.queryByRole("textbox", { name: "Message Alfred" })).toBeNull();
    expect(document.body.textContent).not.toContain("half-typed question");
    expect(auth.calls).toContain("forget");
    expect(auth.calls).not.toContain("signOut");
  });

  it("uses the timeout and warning lengths from the settings", async () => {
    vi.stubEnv("VITE_IDLE_TIMEOUT_MINUTES", "5");
    vi.stubEnv("VITE_IDLE_WARNING_MINUTES", "1");
    useClock();
    signInAs();
    render(<App />);
    await idle(4 * MIN);
    expect(dialog()!.textContent).toContain("You'll be signed out in 1:00.");
    await idle(1 * MIN);
    expect(screen.getByRole("status").textContent).toBe("You were signed out after 5 minutes of inactivity.");
  });
});

describe("picking up where I left off", () => {
  it("after an inactivity sign-out, reopens the same chat with the unsent text", async () => {
    useClock();
    const auth = signInAs();
    seed(server, "a", [["first topic", "first reply"]]);
    localStorage.setItem("convai.sessionIds", JSON.stringify(["a"]));
    render(<App />);
    await settle();
    fireEvent.click(openHistory().getByRole("button", { name: /first topic/ }));
    await settle();
    expect(screen.getByText("first reply")).toBeTruthy();
    fireEvent.change(messageBox(), { target: { value: "and one more thing" } });
    await idle(15 * MIN);
    expect(JSON.parse(sessionStorage.getItem("convai.resume")!)).toEqual({ sessionId: "a", draft: "and one more thing" });

    const box = await returnFromSignIn(auth);
    expect(await screen.findByText("first reply")).toBeTruthy();
    await boxValue(box, "and one more thing");
    expect(sessionStorage.getItem("convai.resume")).toBeNull();
  });

  it("does the same after a failed background renewal", async () => {
    const auth = signInAs();
    seed(server, "a", [["first topic", "first reply"]]);
    localStorage.setItem("convai.sessionIds", JSON.stringify(["a"]));
    render(<App />);
    fireEvent.click(await openHistory().findByRole("button", { name: /first topic/ }));
    await screen.findByText("first reply");
    fireEvent.change(messageBox(), { target: { value: "draft" } });
    act(() => auth.failRenewal());
    expect(await screen.findByText("Your session has ended. Sign in to continue.")).toBeTruthy();
    expect(screen.queryByText("first reply")).toBeNull();

    const box = await returnFromSignIn(auth);
    expect(await screen.findByText("first reply")).toBeTruthy();
    await boxValue(box, "draft");
  });

  it("a new chat with no messages keeps only the draft", async () => {
    useClock();
    const auth = signInAs();
    render(<App />);
    fireEvent.change(messageBox(), { target: { value: "my question" } });
    await idle(15 * MIN);
    expect(JSON.parse(sessionStorage.getItem("convai.resume")!)).toEqual({ sessionId: null, draft: "my question" });
    const box = await returnFromSignIn(auth);
    await boxValue(box, "my question");
    expect(server.calls.some((c) => c.url.includes("/history"))).toBe(false);
  });

  it("a deliberate sign-out forgets the chat and the draft", async () => {
    const auth = signInAs();
    render(<App />);
    sessionStorage.setItem("convai.resume", JSON.stringify({ sessionId: "a", draft: "old" }));
    fireEvent.change(messageBox(), { target: { value: "draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(sessionStorage.getItem("convai.resume")).toBeNull();
    const box = await returnFromSignIn(auth);
    expect((box as HTMLTextAreaElement).value).toBe("");
  });

  it("ignores unreadable saved state", async () => {
    sessionStorage.setItem("convai.resume", "{not json");
    signInAs();
    render(<App />);
    expect(messageBox().value).toBe("");
    expect(sessionStorage.getItem("convai.resume")).toBeNull();
  });
});
