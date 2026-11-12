// Spec 016: the attach screens (Figma "A0 — Attach menu", "A3 — Document attached"). Files are picked and shown
// in the message box but not sent: there is no upload service yet (backlog BL-032).
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { installServer, messageBox, openHistory, signInAs, startChat, type Server } from "./helpers";

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

const attachButton = () => screen.getByRole("button", { name: "Add to the conversation" });
const menu = () => screen.queryByRole("group", { name: "Add to the conversation" });
const uploadInput = () => document.querySelector<HTMLInputElement>('input[type="file"][data-source="device"]')!;
const photoInput = () => document.querySelector<HTMLInputElement>('input[type="file"][data-source="camera"]')!;
const chatPosts = () => server.calls.filter((c) => c.method === "POST" && c.url === "/api/chat");

function file(name: string, type: string, bytes: number) {
  const f = new File(["x"], name, { type });
  Object.defineProperty(f, "size", { value: bytes });
  return f;
}

async function renderApp() {
  render(<App />);
  await act(async () => {});
}

function pick(input: HTMLInputElement, f: File) {
  fireEvent.change(input, { target: { files: [f] } });
}

describe("attach menu (A0)", () => {
  it("opens from the + button with the design's options, and closes on Escape back to the button", async () => {
    await renderApp();
    expect(menu()).toBeNull();
    expect(attachButton().getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(attachButton());
    const m = within(menu()!);
    expect(attachButton().getAttribute("aria-expanded")).toBe("true");
    m.getByText("I’ll read it and use it in my answers.");
    m.getByRole("button", { name: /Upload from device.*PDF, JPG or PNG, up to 10 MB/ });
    m.getByRole("button", { name: /Take a photo.*Snap a pay stub or statement/ });
    m.getByText("Files stay private to your account");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(menu()).toBeNull();
    expect(document.activeElement).toBe(attachButton());
  });

  it("closes when clicking elsewhere, and when + is clicked again", async () => {
    await renderApp();
    fireEvent.click(attachButton());
    fireEvent.mouseDown(document.body);
    expect(menu()).toBeNull();
    fireEvent.click(attachButton());
    fireEvent.click(attachButton());
    expect(menu()).toBeNull();
  });

  it("opens the matching file picker for each option", async () => {
    await renderApp();
    const deviceClick = vi.spyOn(uploadInput(), "click");
    const photoClick = vi.spyOn(photoInput(), "click");
    fireEvent.click(attachButton());
    fireEvent.click(within(menu()!).getByRole("button", { name: /Upload from device/ }));
    expect(deviceClick).toHaveBeenCalled();
    expect(menu()).toBeNull();
    fireEvent.click(attachButton());
    fireEvent.click(within(menu()!).getByRole("button", { name: /Take a photo/ }));
    expect(photoClick).toHaveBeenCalled();

    expect(uploadInput().accept).toBe("application/pdf,image/jpeg,image/png");
    expect(photoInput().accept).toBe("image/jpeg,image/png");
    expect(photoInput().getAttribute("capture")).toBe("environment");
  });
});

describe("document attached (A3)", () => {
  it("shows the chosen file in the message box, ready, with an attachment prompt", async () => {
    await renderApp();
    pick(uploadInput(), file("Q3 2026 statement.pdf", "application/pdf", 1.2 * 1024 * 1024));
    const card = screen.getByRole("group", { name: "Attached file" });
    within(card).getByText("Q3 2026 statement.pdf");
    within(card).getByText("PDF · 1.2 MB · ready");
    expect(messageBox().placeholder).toBe("Ask about this document…");
    expect(screen.getByRole("button", { name: "Add to the conversation" })).toBeTruthy();
  });

  it("shows small files in KB and takes photos as JPG or PNG", async () => {
    await renderApp();
    pick(photoInput(), file("stub.jpg", "image/jpeg", 300 * 1024));
    within(screen.getByRole("group", { name: "Attached file" })).getByText("JPG · 300 KB · ready");
  });

  it("removes the file, back to the normal prompt", async () => {
    await renderApp();
    pick(uploadInput(), file("a.pdf", "application/pdf", 2048));
    fireEvent.click(screen.getByRole("button", { name: "Remove a.pdf" }));
    expect(screen.queryByRole("group", { name: "Attached file" })).toBeNull();
    expect(messageBox().placeholder).toBe("Ask anything about your money…");
  });

  it.each([
    [file("notes.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 1000), /PDF, JPG or PNG/],
    [file("huge.pdf", "application/pdf", 11 * 1024 * 1024), /over 10 MB/],
  ])("refuses %s with a message and attaches nothing", async (f, message) => {
    await renderApp();
    pick(uploadInput(), f);
    expect(screen.getByRole("alert").textContent).toMatch(message);
    expect(screen.queryByRole("group", { name: "Attached file" })).toBeNull();
    pick(uploadInput(), file("ok.pdf", "application/pdf", 10));
    expect(screen.queryByRole("alert")).toBeNull(); // a good file clears the message
  });

  it("says the file isn't sent yet, sends only the text, and clears the file", async () => {
    await renderApp();
    pick(uploadInput(), file("a.pdf", "application/pdf", 2048));
    screen.getByText(/Sending files is coming soon/);
    fireEvent.change(messageBox(), { target: { value: "what is this?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(chatPosts()).toHaveLength(1));
    expect(Object.keys(chatPosts()[0].body as object).sort()).toEqual(["message", "session_id"]);
    expect(screen.queryByRole("group", { name: "Attached file" })).toBeNull();
    expect(messageBox().placeholder).toBe("Ask anything about your money…");
  });

  it("keeps the file when Send is pressed with nothing typed", async () => {
    await renderApp();
    pick(uploadInput(), file("a.pdf", "application/pdf", 2048));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(chatPosts()).toHaveLength(0);
    screen.getByRole("group", { name: "Attached file" });
  });


  it("doesn't carry the file into a new chat or into another chat opened from History", async () => {
    await renderApp();
    await startChat("first");
    pick(uploadInput(), file("a.pdf", "application/pdf", 2048));
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByRole("group", { name: "Attached file" })).toBeNull();
    expect(messageBox().placeholder).toBe("Ask anything about your money…");

    await startChat("second");
    pick(uploadInput(), file("b.pdf", "application/pdf", 2048));
    fireEvent.click(await openHistory().findByText("first"));
    await waitFor(() => expect(screen.queryByRole("group", { name: "Attached file" })).toBeNull());
  });
});
