// Spec 005 UI, restyled as full-page Alfred: branding, welcome + suggestions, Markdown replies, disclaimer note.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { greetingFor } from "../chat/Welcome";
import { installServer, messageBox, openHistory, seed, signInAs, type Server } from "./helpers";

const KEY = "convai.sessionIds";
let server: Server;

const shownMessages = () =>
  Array.from(document.querySelectorAll(".message")).map((el) => el.textContent ?? "");

async function openSeeded(reply: string) {
  seed(server, "s", [["question", reply]]);
  localStorage.setItem(KEY, JSON.stringify(["s"]));
  render(<App />);
  fireEvent.click(await openHistory().findByRole("button", { name: /question/ }));
  await waitFor(() => expect(shownMessages()).toHaveLength(2));
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

describe("branding", () => {
  it("shows the Alfred header with the signed-in member and Sign out", () => {
    render(<App />);
    const banner = screen.getByRole("banner");
    expect(within(banner).getByRole("heading", { level: 1 }).textContent).toBe("Alfred");
    expect(banner.textContent).toContain("Vinod");
    expect(within(banner).getByRole("button", { name: "Sign out" })).toBeTruthy();
  });

  it("puts the header above the rail, and the rail before the chat", () => {
    render(<App />);
    const banner = screen.getByRole("banner");
    const rail = screen.getByRole("navigation", { name: "Alfred" });
    const chat = screen.getByRole("main");
    expect(banner.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(rail.compareDocumentPosition(chat) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("marks Notifications as coming soon instead of leaving a dead button", () => {
    render(<App />);
    const button = screen.getByRole("button", { name: /notifications/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.getAttribute("aria-label")).toMatch(/coming soon/);
  });
});

describe("welcome screen", () => {
  it("greets the member by name for the time of day", () => {
    render(<App />);
    const greeting = screen.getByRole("heading", { level: 2, name: /vinod/i });
    expect(greeting.textContent).toBe(`${greetingFor(new Date())}, Vinod.`);
    expect(greetingFor(new Date(2026, 0, 1, 9))).toBe("Good morning");
    expect(greetingFor(new Date(2026, 0, 1, 14))).toBe("Good afternoon");
    expect(greetingFor(new Date(2026, 0, 1, 20))).toBe("Good evening");
  });

  it("starts at the greeting, and scrolls to the newest message once the chat has messages", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    try {
      render(<App />);
      expect(scroll).not.toHaveBeenCalled();
      fireEvent.change(messageBox(), { target: { value: "hello" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
      await waitFor(() => expect(shownMessages()).toHaveLength(2));
      expect(scroll).toHaveBeenCalled();
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("offers suggested questions on an empty chat and sends one when clicked", async () => {
    render(<App />);
    expect(screen.getAllByRole("button", { name: /\?|years/ }).length).toBe(4);
    fireEvent.click(screen.getByRole("button", { name: /What is my portfolio worth\?/ }));
    await waitFor(() =>
      expect(shownMessages()).toEqual([
        "What is my portfolio worth?",
        "(mock) You said: What is my portfolio worth?",
      ]),
    );
    expect(screen.queryByRole("button", { name: /What is my portfolio worth\?/ })).toBeNull();
  });
});

describe("assistant replies", () => {
  it("render Markdown lists and bold instead of raw symbols", async () => {
    await openSeeded("You hold:\n- **VTI** $30,000\n- BND $18,000");
    const reply = document.querySelectorAll(".message")[1];
    expect(Array.from(reply.querySelectorAll("li")).map((li) => li.textContent)).toEqual([
      "VTI $30,000",
      "BND $18,000",
    ]);
    expect(reply.querySelector("strong")!.textContent).toBe("VTI");
  });

  it("show a trailing _italic_ disclaimer as a separate note, outside the reply", async () => {
    await openSeeded("Your portfolio is worth $70,000.\n\n_Demo data, not financial advice._");
    expect(shownMessages()[1]).toBe("Your portfolio is worth $70,000.");
    const note = document.querySelector(".disclaimer")!;
    expect(note.textContent).toBe("Demo data, not financial advice.");
    expect(document.body.textContent).not.toContain("_Demo");
  });

  it("keep user messages as plain text", async () => {
    render(<App />);
    fireEvent.change(messageBox(), { target: { value: "- not a list" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(shownMessages()[0]).toBe("- not a list"));
    expect(document.querySelectorAll(".message")[0].querySelector("li")).toBeNull();
  });

  it("show the time of each of the member's messages, with a copy button", async () => {
    await openSeeded("answer");
    const time = screen.getByRole("main").querySelector("time[datetime]")!;
    expect(time.getAttribute("datetime")).toMatch(/^2026-11-04T09:00/);
    expect(screen.getAllByRole("button", { name: "Copy message" })).toHaveLength(1);
  });
});
