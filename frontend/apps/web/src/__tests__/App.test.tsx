import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { history, installServer, messageBox, openHistory, seed, signInAs, startChat, type Server } from "./helpers";

const KEY = "convai.sessionIds";
let server: Server;

function storedIds(): string[] {
  return JSON.parse(localStorage.getItem(KEY) ?? "[]");
}

function shownMessages(): string[] {
  return Array.from(document.querySelectorAll(".message")).map((el) => el.textContent ?? "");
}

const chatPosts = () => server.calls.filter((c) => c.method === "POST" && c.url === "/api/chat");

function sidebarTitles(): string[] {
  return Array.from(document.querySelectorAll(".session-title")).map((el) => el.textContent ?? "");
}

async function send(text: string) {
  fireEvent.change(messageBox(), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

async function openChat(title: string) {
  fireEvent.click(history().getByRole("button", { name: new RegExp(title) }));
}

beforeEach(() => {
  localStorage.clear();
  signInAs();
  server = installServer();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("US1: see and reopen a past conversation", () => {
  it("lists this browser's stored conversations, newest first", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    seed(server, "b", [["second topic", "(mock) You said: second topic"]]);
    seed(server, "other-browser", [["not mine", "(mock) You said: not mine"]]);
    localStorage.setItem(KEY, JSON.stringify(["a", "b"]));

    render(<App />);
    expect(shownMessages()).toEqual([]); // page load opens a fresh chat, on the homepage (no rail)
    await startChat();
    openHistory();

    await waitFor(() => expect(sidebarTitles()).toEqual(["hello", "second topic", "first topic"]));
  });

  it("shows the empty state when this browser has no conversations yet", async () => {
    server.holdChat = new Promise<void>(() => {}); // the first reply never arrives, so nothing is stored
    render(<App />);
    await send("first ever");
    openHistory(); // the rail shows as soon as a chat starts
    expect(await screen.findByText(/no past chats yet/i)).toBeTruthy();
    expect(server.calls.filter((c) => c.url.startsWith("/api/sessions"))).toEqual([]);
  });

  it("reopens a conversation with every message in order, including mock replies", async () => {
    seed(server, "a", [
      ["first topic", "(mock) You said: first topic"],
      ["more", "(mock) You said: more"],
    ]);
    localStorage.setItem(KEY, JSON.stringify(["a"]));
    render(<App />);
    await startChat();
    openHistory();
    await screen.findByText("first topic");

    await openChat("first topic");

    await waitFor(() =>
      expect(shownMessages()).toEqual([
        "first topic",
        "(mock) You said: first topic",
        "more",
        "(mock) You said: more",
      ]),
    );
    const entry = history().getByRole("button", { name: /first topic/ });
    expect(entry.getAttribute("aria-current")).toBe("true");
  });

  it("keeps the current chat and offers Retry when a conversation fails to load", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["a"]));
    render(<App />);
    await send("current chat");
    await waitFor(() => expect(shownMessages()).toContain("(mock) You said: current chat"));
    openHistory();
    await screen.findByText("first topic");

    server.failHistory = true;
    await openChat("first topic");

    expect((await screen.findByRole("alert")).textContent).toMatch(/couldn't open/i);
    expect(shownMessages()).toEqual(["current chat", "(mock) You said: current chat"]);

    server.failHistory = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() =>
      expect(shownMessages()).toEqual(["first topic", "(mock) You said: first topic"]),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers Retry when the conversation list fails to load", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["a"]));
    server.failList = true;
    render(<App />);
    await startChat();
    openHistory();

    expect((await screen.findByRole("alert")).textContent).toMatch(/couldn't load/i);
    server.failList = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(sidebarTitles()).toEqual(["hello", "first topic"]));
  });

  it("stores a new conversation and lists it after its first message", async () => {
    render(<App />);
    await send("brand new");
    await screen.findByText("(mock) You said: brand new");
    openHistory();

    await waitFor(() => expect(sidebarTitles()).toEqual(["brand new"]));
    expect(storedIds()).toHaveLength(1);
    const posted = server.calls.find((c) => c.method === "POST")!;
    expect((posted.body as { session_id: string }).session_id).toBe(storedIds()[0]);
  });
});


describe("US2: continue a reopened conversation", () => {
  it("adds new messages to the reopened conversation and moves it to the top", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    seed(server, "b", [["second topic", "(mock) You said: second topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["b", "a"]));
    render(<App />);
    await startChat();
    openHistory();
    await waitFor(() => expect(sidebarTitles()).toEqual(["hello", "second topic", "first topic"]));

    await openChat("first topic");
    await waitFor(() => expect(shownMessages()).toHaveLength(2));
    await send("follow-up");

    await waitFor(() =>
      expect(shownMessages()).toEqual([
        "first topic",
        "(mock) You said: first topic",
        "follow-up",
        "(mock) You said: follow-up",
      ]),
    );
    expect((chatPosts().at(-1)!.body as { session_id: string }).session_id).toBe("a");
    expect(storedIds()[0]).toBe("a");
    expect(storedIds()).toHaveLength(3);
    await waitFor(() => expect(sidebarTitles()).toEqual(["first topic", "hello", "second topic"]));
  });

  it("never shows a late reply in a different conversation", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    seed(server, "b", [["second topic", "(mock) You said: second topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["b", "a"]));
    render(<App />);
    await startChat();
    openHistory();
    await screen.findByText("first topic");
    await openChat("first topic");
    await waitFor(() => expect(shownMessages()).toHaveLength(2));

    let release!: () => void;
    server.holdChat = new Promise<void>((r) => (release = r));
    await send("slow question");
    await waitFor(() => expect(document.querySelector(".pending")).not.toBeNull());

    await openChat("second topic");
    await waitFor(() =>
      expect(shownMessages()).toEqual(["second topic", "(mock) You said: second topic"]),
    );
    expect(document.querySelector(".pending")).toBeNull(); // A's pending reply isn't shown in B

    await act(async () => {
      release();
    });
    await waitFor(() => expect(sidebarTitles()[0]).toBe("first topic")); // A was active last
    expect(shownMessages()).toEqual(["second topic", "(mock) You said: second topic"]);

    server.holdChat = null;
    await openChat("first topic");
    await waitFor(() =>
      expect(shownMessages()).toEqual([
        "first topic",
        "(mock) You said: first topic",
        "slow question",
        "(mock) You said: slow question",
      ]),
    );
  });

  it("shows the full thread when the user returns before a late reply arrives", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    seed(server, "b", [["second topic", "(mock) You said: second topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["b", "a"]));
    render(<App />);
    await startChat();
    openHistory();
    await screen.findByText("first topic");
    await openChat("first topic");
    await waitFor(() => expect(shownMessages()).toHaveLength(2));

    let release!: () => void;
    server.holdChat = new Promise<void>((r) => (release = r));
    await send("slow question");
    await openChat("second topic");
    await waitFor(() => expect(shownMessages()[0]).toBe("second topic"));
    await openChat("first topic"); // back to A before the reply; history doesn't have it yet
    await waitFor(() => expect(shownMessages()).toEqual(["first topic", "(mock) You said: first topic"]));

    server.holdChat = null;
    await act(async () => {
      release();
    });

    await waitFor(() =>
      expect(shownMessages()).toEqual([
        "first topic",
        "(mock) You said: first topic",
        "slow question",
        "(mock) You said: slow question",
      ]),
    );
  });
});

describe("US3: start a new conversation", () => {
  it("clears the chat, adds nothing until the first send, and leaves the old chat unchanged", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["a"]));
    render(<App />);
    await startChat();
    openHistory();
    await screen.findByText("first topic");
    await openChat("first topic");
    await waitFor(() => expect(shownMessages()).toHaveLength(2));
    const before = storedIds();

    fireEvent.click(screen.getByRole("button", { name: "New chat" }));

    expect(shownMessages()).toEqual([]);
    expect(storedIds()).toEqual(before);
    expect(screen.queryByRole("navigation", { name: "Alfred" })).toBeNull(); // back on the homepage

    await send("new topic");

    await waitFor(() => expect(sidebarTitles()).toEqual(["new topic", "hello", "first topic"]));
    expect(history().getByRole("button", { name: /first topic/ }).getAttribute("aria-current")).toBeNull();
    const ids = storedIds();
    expect(ids).toHaveLength(3);
    expect(before).not.toContain(ids[0]);

    await openChat("first topic");
    await waitFor(() =>
      expect(shownMessages()).toEqual(["first topic", "(mock) You said: first topic"]),
    );
  });
});

describe("History panel", () => {
  it("starts closed and opens and closes from the rail's History button", async () => {
    render(<App />);
    await startChat();
    const toggle = screen.getByRole("button", { name: "History" });
    const layout = document.querySelector(".layout")!;
    expect(screen.queryByRole("navigation", { name: "Past chats" })).toBeNull();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(toggle);
    expect(await history().findByRole("button", { name: /hello/ })).toBeTruthy();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(layout.classList.contains("open")).toBe(true);

    fireEvent.click(toggle);
    expect(screen.queryByRole("navigation", { name: "Past chats" })).toBeNull();
    expect(layout.classList.contains("open")).toBe(false);
  });

  it("closes when tapping outside it on a narrow screen", async () => {
    render(<App />);
    await startChat();
    await openHistory().findByRole("button", { name: /hello/ });
    const layout = document.querySelector(".layout")!;
    expect(layout.classList.contains("open")).toBe(true);

    fireEvent.click(document.querySelector(".backdrop")!);
    expect(layout.classList.contains("open")).toBe(false);
    expect(document.querySelector(".backdrop")).toBeNull();
  });

  it("shows a failed chat list load in the chat when the panel is closed", async () => {
    seed(server, "a", [["first topic", "(mock) You said: first topic"]]);
    localStorage.setItem(KEY, JSON.stringify(["a"]));
    server.failList = true;
    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toMatch(/couldn't load past chats/i);
    server.failList = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    await startChat();
    expect(await openHistory().findByRole("button", { name: /first topic/ })).toBeTruthy();
  });
});
