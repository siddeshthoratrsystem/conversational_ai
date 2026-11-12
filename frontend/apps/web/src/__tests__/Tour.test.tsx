// The guided tour from the homepage's "Start guided tour" button (Figma "Flow / Guided tour" 1–7).
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { installServer, signInAs } from "./helpers";

beforeEach(() => {
  localStorage.clear();
  signInAs();
  installServer();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const tour = () => screen.queryByRole("dialog", { name: "Guided tour" });
const callout = () => within(tour()!);
const next = () => fireEvent.click(callout().getByRole("button", { name: /^(Next|Done)$/ }));
const tasksPage = () => screen.queryByRole("region", { name: "Guided tasks" });

async function startTour() {
  render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Start guided tour" }));
}

describe("guided tour", () => {
  it("is not running until the button is pressed", async () => {
    render(<App />);
    await act(async () => {});
    expect(tour()).toBeNull();
    screen.getByRole("button", { name: "Start guided tour" });
  });

  it("walks the seven steps with the design's copy, then Done ends it on the Guided tasks page", async () => {
    await startTour();
    const steps: [string, RegExp][] = [
      ["1 / 7", /your AI financial assistant\. Let me show you quickly how this works\./],
      ["2 / 7", /These cards are your starting points/],
      ["3 / 7", /You can type to me, or tap here to just talk instead/],
      ["4 / 7", /Try saying something, then tap here again/],
      ["5 / 7", /I can also take care of things for you in the background/],
      ["6 / 7", /Here you’ll find things I can set up to run automatically/],
      ["7 / 7", /That's the tour\. Ask me anything in the chat/],
    ];
    for (const [count, text] of steps) {
      callout().getByText(count);
      callout().getByText(text);
      if (count === "7 / 7") callout().getByRole("button", { name: "Done" });
      next();
    }
    expect(tour()).toBeNull();
    expect(tasksPage()).not.toBeNull();
  });

  it("puts focus on Next at every step", async () => {
    await startTour();
    expect(document.activeElement).toBe(callout().getByRole("button", { name: "Next" }));
    next();
    expect(document.activeElement).toBe(callout().getByRole("button", { name: "Next" }));
  });

  it("shows the listening state on step 4 only", async () => {
    await startTour();
    next();
    next();
    expect(screen.queryByText("Listening…")).toBeNull();
    screen.getByRole("button", { name: "Send" });
    next();
    screen.getByText("Listening…");
    screen.getByRole("button", { name: "End voice" });
    next();
    expect(screen.queryByText("Listening…")).toBeNull();
    screen.getByRole("button", { name: "Send" });
  });

  it("opens the Guided tasks page with the rail on step 6", async () => {
    await startTour();
    for (let i = 0; i < 5; i++) next();
    callout().getByText("6 / 7");
    expect(tasksPage()).not.toBeNull();
    screen.getByRole("button", { name: "Tasks" });
  });

  it("ends on Skip tour, and on Escape without closing the Guided tasks page under it", async () => {
    await startTour();
    next();
    fireEvent.click(callout().getByRole("button", { name: "Skip tour" }));
    expect(tour()).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Start guided tour" }));
    callout().getByText("1 / 7");
    for (let i = 0; i < 5; i++) next();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(tour()).toBeNull();
    expect(tasksPage()).not.toBeNull();
  });

  it("sends nothing while it runs", async () => {
    const fetch = vi.mocked(globalThis.fetch);
    await startTour();
    const before = fetch.mock.calls.length;
    for (let i = 0; i < 7; i++) next();
    expect(fetch.mock.calls.length).toBe(before);
  });
});
