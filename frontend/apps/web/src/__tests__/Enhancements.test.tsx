// Spec 005 UI, restyled as full-page Alfred: branding, welcome + suggestions, Markdown replies, disclaimer note.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { blend } from "../chat/Flock";
import { greetingFor } from "../chat/Welcome";
import { installServer, messageBox, openHistory, seed, signInAs, startChat, type Server } from "./helpers";

const KEY = "convai.sessionIds";
let server: Server;

const shownMessages = () =>
  Array.from(document.querySelectorAll(".message")).map((el) => el.textContent ?? "");

async function openSeeded(reply: string) {
  seed(server, "s", [["question", reply]]);
  localStorage.setItem(KEY, JSON.stringify(["s"]));
  render(<App />);
  await startChat("warm-up");
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

  it("puts the header above the rail, and the rail before the chat", async () => {
    render(<App />);
    await startChat();
    const banner = screen.getByRole("banner");
    const rail = screen.getByRole("navigation", { name: "Alfred" });
    const chat = screen.getByRole("main");
    expect(banner.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(rail.compareDocumentPosition(chat) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("has no rail on the homepage; it appears once a chat starts and goes again on New chat (spec 016)", async () => {
    let release!: () => void;
    server.holdChat = new Promise<void>((r) => (release = r));
    render(<App />);
    const rail = () => screen.queryByRole("navigation", { name: "Alfred" });
    expect(rail()).toBeNull();

    fireEvent.change(messageBox(), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(rail()).not.toBeNull()); // shown while the first reply is pending
    await act(async () => release());
    await screen.findByText("(mock) You said: hello");
    expect(rail()).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(document.querySelector(".layout")!.classList.contains("open")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(rail()).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Past chats" })).toBeNull(); // the panel goes with the rail
    expect(document.querySelector(".layout")!.classList.contains("open")).toBe(false);
  });

  it("has the design's rail: logo for New chat, labelled Chat / Tasks / History tabs, and the avatar", async () => {
    render(<App />);
    await startChat();
    const rail = within(screen.getByRole("navigation", { name: "Alfred" }));
    expect(rail.getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual([
      "New chat",
      "Chat",
      "Tasks",
      "History",
    ]);
    expect(rail.queryByRole("button", { name: /notifications/i })).toBeNull(); // hidden in the design
    expect(rail.getByText("V")).toBeTruthy(); // avatar initial
  });

  it("marks Chat as the current tab, and Tasks while the Guided tasks page is open; Chat goes back to the chat", async () => {
    render(<App />);
    await startChat();
    const chatTab = () => screen.getByRole("button", { name: "Chat" });
    expect(chatTab().getAttribute("aria-current")).toBe("page");

    fireEvent.click(screen.getByRole("button", { name: "Tasks" }));
    expect(screen.getByRole("region", { name: "Guided tasks" })).toBeTruthy();
    expect(chatTab().getAttribute("aria-current")).toBeNull();

    fireEvent.click(chatTab());
    expect(screen.queryByRole("region", { name: "Guided tasks" })).toBeNull();
    expect(chatTab().getAttribute("aria-current")).toBe("page");
    screen.getByText("(mock) You said: hello"); // same conversation
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

  it("shows the Figma murmuration (Flock) above the greeting, hidden from screen readers", () => {
    render(<App />);
    const flock = screen.getByRole("main").querySelector("svg.text-flock")!;
    expect(flock.querySelectorAll("circle")).toHaveLength(320);
    expect(flock.closest("[aria-hidden]")).not.toBeNull();
  });

  it("keeps the flock moving on the homepage, and stops it once a chat starts", async () => {
    const raf = vi.fn(() => 7);
    const cancel = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("cancelAnimationFrame", cancel);
    render(<App />);
    expect(raf).toHaveBeenCalled();
    await startChat();
    expect(cancel).toHaveBeenCalledWith(7);
  });

  it("never holds the flock in place: its shape changes in every part of the loop", () => {
    for (let t = 0; t < 18; t += 0.25) {
      if (Math.abs(t % 4.5) < 1e-9) continue; // the turning points at the cloud and the sphere
      expect(blend(t + 0.05)).not.toBeCloseTo(blend(t), 4);
    }
  });

  it("leaves the flock still when the member prefers reduced motion", () => {
    const raf = vi.fn(() => 1);
    vi.stubGlobal("requestAnimationFrame", raf);
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce") }));
    render(<App />);
    expect(raf).not.toHaveBeenCalled();
  });

  it("shows the plan update line under the greeting", () => {
    render(<App />);
    screen.getByText(
      "Your plan moved this week: savings are up $120, and retirement still needs attention. Where shall we start?",
    );
  });

  it("shows the four starter cards with the design's copy, in order (spec 016 FR-003)", () => {
    render(<App />);
    const cards = screen.getAllByRole("article");
    expect(cards.map((card) => within(card).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "You’re $500K short of your retirement goal",
      "Your Chase savings has $3,200 earning nothing",
      "Pay off your debt faster than you think",
      "Put your finances on autopilot",
    ]);
    expect(cards.map((card) => card.querySelector("svg.lucide")!.getAttribute("class"))).toEqual([
      expect.stringContaining("lucide-chart-line"),
      expect.stringContaining("lucide-sprout"),
      expect.stringContaining("lucide-trending-down"),
      expect.stringContaining("lucide-zap"), // lightning, as in the design
    ]);
    within(cards[0]).getByText("Increasing your 401(k) contribution by $220 a month closes that gap by retirement.");
    within(cards[1]).getByText("There's likely a better place for that money to sit, want to see?");
    within(cards[2]).getByText("I'll build a personalized payoff plan that fits your monthly budget.");
    within(cards[3]).getByText(
      "I can watch for overspending, send a monthly spend report, and more, without you having to ask.",
    );
    expect(cards.map((card) => within(card).getByRole("button").textContent)).toEqual([
      "Close the gap",
      "Tell me more",
      "Build my plan",
      "Explore automations",
    ]);
  });

  it.each([
    ["Close the gap: You’re $500K short of your retirement goal", "How can I close the $500K gap in my retirement savings?"],
    ["Tell me more: Your Chase savings has $3,200 earning nothing", "Where could the $3,200 in my Chase savings earn more?"],
    ["Build my plan: Pay off your debt faster than you think", "Build me a plan to pay off my debt faster."],
    ["Explore automations: Put your finances on autopilot", "What could you automate for my finances?"],
  ])("sends the starter prompt when %s is clicked", async (button, prompt) => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: button }));
    await waitFor(() => expect(shownMessages()).toEqual([prompt, `(mock) You said: ${prompt}`]));
    expect(screen.queryAllByRole("article")).toEqual([]);
  });

  it("has no coming-soon starters left: every card's button is enabled", () => {
    render(<App />);
    const buttons = screen.getAllByRole("article").map((card) => within(card).getByRole("button") as HTMLButtonElement);
    expect(buttons.filter((b) => b.disabled)).toEqual([]);
    expect(screen.queryByText("Coming soon")).toBeNull();
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

  it("show the time under each of Alfred's replies, for reopened and new chats alike", async () => {
    await openSeeded("answer");
    const times = () => Array.from(screen.getByRole("main").querySelectorAll("time[datetime]"));
    expect(times().map((t) => t.getAttribute("datetime"))).toEqual([
      expect.stringMatching(/^2026-11-04T09:00/), // question
      expect.stringMatching(/^2026-11-04T09:00/), // answer
    ]);
    expect(times()[1].closest(".flex-col")!.querySelector(".message")!.textContent).toBe("answer");

    const before = Date.now();
    fireEvent.change(messageBox(), { target: { value: "more" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("(mock) You said: more");
    const replyTime = times().at(-1)!;
    expect(Date.parse(replyTime.getAttribute("datetime")!)).toBeGreaterThanOrEqual(before - 1000);
    expect(replyTime.textContent).toMatch(/\d/);
    expect(times()).toHaveLength(4);
  });

  it("copy the member's message to the clipboard and confirm it, then reset", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    await openSeeded("answer");
    fireEvent.click(screen.getByRole("button", { name: "Copy message" }));
    expect(writeText).toHaveBeenCalledWith("question");
    await screen.findByRole("button", { name: "Copied" });
    await screen.findByRole("button", { name: "Copy message" }, { timeout: 3000 }); // back after 2 s
  });

  it("still copy where the clipboard API is unavailable (not a secure page)", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
    let copied = "";
    const execCommand = vi.fn(() => {
      copied = (document.activeElement as HTMLTextAreaElement).value;
      return true;
    });
    document.execCommand = execCommand;
    try {
      await openSeeded("answer");
      fireEvent.click(screen.getByRole("button", { name: "Copy message" }));
      await screen.findByRole("button", { name: "Copied" });
      expect(execCommand).toHaveBeenCalledWith("copy");
      expect(copied).toBe("question");
      expect(document.querySelectorAll("textarea")).toHaveLength(1); // only the message box is left
    } finally {
      delete (document as { execCommand?: unknown }).execCommand;
    }
  });
});
