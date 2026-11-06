// Spec 009 US1: a 401 during use renews once, then ends the session.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { setAuthClient } from "../auth/client";
import { installServer, openHistory, seed, signInAs, type Server } from "./helpers";

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
});

describe("401 while signed in", () => {
  it("renews once and retries the call", async () => {
    const auth = signInAs();
    seed(server, "a", [["first topic", "reply"]]);
    localStorage.setItem("convai.sessionIds", JSON.stringify(["a"]));
    server.rejectAuth = true;
    auth.renew = async () => {
      auth.calls.push("renew");
      server.rejectAuth = false; // the new token is accepted
      auth.token = "token-1";
      return true;
    };
    render(<App />);
    expect(await openHistory().findByText("first topic")).toBeTruthy();
    expect(auth.calls).toContain("renew");
    expect(server.authHeaders.at(-1)).toBe("Bearer token-1");
  });

  it("ends the session when renewal fails, clearing the screen", async () => {
    const auth = signInAs();
    auth.renewSucceeds = false;
    server.rejectAuth = true;
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in to Alfred" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Your session has ended. Sign in to continue.");
    expect(screen.queryByRole("textbox", { name: "Message Alfred" })).toBeNull();
    await waitFor(() => expect(auth.calls).toContain("forget"));
  });
});
