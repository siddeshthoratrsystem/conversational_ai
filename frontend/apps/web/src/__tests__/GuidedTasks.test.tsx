// Spec 010: the Tasks rail button opens the Guided tasks overlay (static content, inert rows).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { installServer, messageBox, openHistory, seed, signInAs, type Server } from "./helpers";

let server: Server;

// Spec FR-004, word for word (the what-if description keeps the design's missing closing quote).
const SECTIONS: [string, [string, string][]][] = [
  [
    "Budgeting",
    [
      ["Get a heads-up before you overspend", "A standing alert tied to your category targets."],
      ["Catch a cash shortfall before it happens", "Forecasting your balance against what's coming."],
      ["Get a monthly spending report, automatically", "A recurring readout, no need to ask."],
      ["Find out if you're overpaying on your bills", "A standing check against current offers."],
    ],
  ],
  [
    "Retirement",
    [
      [
        "Automatically raise your 401(k) contribution every year",
        "Set a rule, like raising it 1% every January or whenever you get a raise, up to a cap you choose.",
      ],
      [
        "Make sure your investments still match your risk tolerance",
        "A standing check across your retirement and taxable accounts.",
      ],
      ["Run what-if scenarios on your retirement plan", "Ask things like “what if I retire at 62 and move somewhere cheaper."],
    ],
  ],
  [
    "Debt",
    [
      ["Put your debt payoff on autopilot", "Pick avalanche, snowball, or a custom strategy."],
      ["Get notified when refinancing could save you money", "A standing watch on rates and offers against your profile."],
      [
        "Compare debt payoff strategies side by side",
        "See total interest, your debt-free date, and what extra payments change.",
      ],
    ],
  ],
  [
    "Savings",
    [
      [
        "Roll an old 401(k) into one place",
        "Tell me where your old plan is and I’ll handle the paperwork and the call to your former provider.",
      ],
    ],
  ],
];

const tasksButton = () => screen.getByRole("button", { name: "Tasks" });
const overlay = () => screen.queryByRole("region", { name: "Guided tasks" });

function openTasks() {
  fireEvent.click(tasksButton());
  return within(screen.getByRole("region", { name: "Guided tasks" }));
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

describe("Guided tasks overlay: browse (US1)", () => {
  it("enables the Tasks rail button, closed to start", () => {
    render(<App />);
    expect((tasksButton() as HTMLButtonElement).disabled).toBe(false);
    expect(tasksButton().getAttribute("aria-expanded")).toBe("false");
    expect(overlay()).toBeNull();
  });

  it("shows the heading, intro and every section and task with the design's copy", () => {
    render(<App />);
    const region = openTasks();

    expect(region.getByRole("heading", { level: 2 }).textContent).toBe("Guided tasks");
    region.getByText("Guided tasks I can take you through, start to finish. Pick one and I’ll do the heavy lifting.");
    expect(region.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(
      SECTIONS.map(([title]) => title),
    );

    const lists = region.getAllByRole("list");
    expect(lists).toHaveLength(SECTIONS.length);
    SECTIONS.forEach(([, tasks], i) => {
      const items = within(lists[i]).getAllByRole("listitem");
      expect(items).toHaveLength(tasks.length);
      tasks.forEach(([title, description], j) => {
        within(items[j]).getByText(title);
        within(items[j]).getByText(description);
      });
    });
  });

  it("keeps the header and rail, and marks Tasks as open", () => {
    render(<App />);
    openTasks();
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Alfred" })).toBeTruthy();
    expect(tasksButton().getAttribute("aria-expanded")).toBe("true");
    expect(tasksButton().getAttribute("aria-controls")).toBe("guided-tasks");
  });
});

describe("Guided tasks overlay: leave (US2)", () => {
  it("stays open when Tasks is selected again", () => {
    render(<App />);
    openTasks();
    fireEvent.click(tasksButton());
    expect(overlay()).not.toBeNull();
    expect(tasksButton().getAttribute("aria-expanded")).toBe("true");
  });

  it("closes on Escape and returns focus to the Tasks button", () => {
    render(<App />);
    openTasks();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(overlay()).toBeNull();
    expect(document.activeElement).toBe(tasksButton());
  });

  it("closes on New chat", () => {
    render(<App />);
    openTasks();
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(overlay()).toBeNull();
  });

  it("closes once a chat picked from History has loaded", async () => {
    seed(server, "s", [["earlier question", "earlier answer"]]);
    localStorage.setItem("convai.sessionIds", JSON.stringify(["s"]));
    render(<App />);
    openTasks();
    fireEvent.click(await openHistory().findByRole("button", { name: /earlier question/ }));
    await waitFor(() => expect(overlay()).toBeNull());
    screen.getByText("earlier answer");
  });

  it("keeps the conversation and the unsent draft", async () => {
    render(<App />);
    fireEvent.change(messageBox(), { target: { value: "first" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("(mock) You said: first");
    fireEvent.change(messageBox(), { target: { value: "half typed" } });

    openTasks();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(overlay()).toBeNull();

    screen.getByText("(mock) You said: first");
    expect(messageBox().value).toBe("half typed");
  });
});

describe("Guided tasks overlay: inert parts (US3)", () => {
  it("has no buttons or links inside the overlay", () => {
    render(<App />);
    const region = openTasks();
    expect(region.queryAllByRole("button")).toEqual([]);
    expect(region.queryAllByRole("link")).toEqual([]);
  });

  it("does nothing when a task row or its ⋯ marker is clicked", () => {
    render(<App />);
    const region = openTasks();
    const before = server.calls.length;
    const row = region.getAllByRole("listitem")[0];
    fireEvent.click(row);
    fireEvent.click(row.querySelector("[data-more]")!);
    expect(server.calls.length).toBe(before);
    expect(overlay()).not.toBeNull();
  });
});
