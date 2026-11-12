import { fireEvent, screen, within } from "@testing-library/react";
import { vi } from "vitest";

import type { HistoryMessage, SessionSummary } from "@convai/core";

/** Start signed in (sign-in keeps the username and access token in localStorage). */
export function signInAs(username = "vinod.patil@example.com", token = "test-token") {
  localStorage.setItem("convai.user", JSON.stringify({ username, token }));
}

/** The stand-in identity provider's token endpoint (spec 008). */
export const TOKEN_URL = "http://localhost:8090/default/token";

/** Alfred's message box. */
export const messageBox = () => screen.getByRole("textbox", { name: "Message Alfred" }) as HTMLTextAreaElement;

/**
 * Send a message and wait for its reply. The homepage has no rail (spec 016), so tests that use History or
 * Tasks start a chat first. Adds a conversation titled `text`.
 */
export async function startChat(text = "hello") {
  fireEvent.change(messageBox(), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText(`(mock) You said: ${text}`);
}

/** Open the History panel from the rail (it starts closed) and return queries scoped to it. */
export function openHistory() {
  if (!screen.queryByRole("navigation", { name: "Past chats" })) {
    fireEvent.click(screen.getByRole("button", { name: "History" }));
  }
  return within(screen.getByRole("navigation", { name: "Past chats" }));
}

/** Queries scoped to the (already open) History panel. */
export const history = () => within(screen.getByRole("navigation", { name: "Past chats" }));

export type Server = {
  sessions: Map<string, { title: string; messages: HistoryMessage[]; lastActive: number }>;
  failHistory: boolean;
  failList: boolean;
  /** When set, POST /api/chat waits for this promise before answering. */
  holdChat: Promise<void> | null;
  calls: { method: string; url: string; body?: unknown; auth?: string | null }[];
  /** Spec 008: token requests received, as form fields. */
  tokenRequests: Record<string, string>[];
  /** Spec 008: when true, the token endpoint answers 500. */
  failToken: boolean;
  /** Spec 008: when true, every /api/* call answers 401. */
  rejectToken: boolean;
  /** Spec 004: last feedback body stored per message id. */
  feedback: Map<number, unknown>;
  /** Spec 004: when true, the feedback endpoint answers 500. */
  failFeedback: boolean;
  /** Spec 004: when set, the feedback endpoint waits for this promise before answering. */
  holdFeedback: Promise<void> | null;
};

let nextId = 1;
let clock = 0;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function message(role: "user" | "assistant", content: string): HistoryMessage {
  return {
    id: nextId++,
    role,
    content,
    intent: null,
    latency_ms: null,
    source: role === "assistant" ? "mock" : null,
    created_at: new Date(Date.UTC(2026, 10, 4, 9, 0, clock++)).toISOString(),
  };
}

/** Seed a stored conversation, as if it had been chatted earlier. */
export function seed(server: Server, id: string, turns: [string, string][]) {
  const messages = turns.flatMap(([u, a]) => [message("user", u), message("assistant", a)]);
  server.sessions.set(id, { title: turns[0][0], messages, lastActive: clock++ });
}

/** A fake backend behind a mocked global fetch, following the README / sessions-api contract. */
export function installServer(): Server {
  const server: Server = {
    sessions: new Map(),
    failHistory: false,
    failList: false,
    holdChat: null,
    calls: [],
    tokenRequests: [],
    failToken: false,
    rejectToken: false,
    feedback: new Map(),
    failFeedback: false,
    holdFeedback: null,
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const method = init?.method ?? "GET";

      if (method === "POST" && url.href === TOKEN_URL) {
        const form = Object.fromEntries(new URLSearchParams(String(init?.body)));
        server.tokenRequests.push(form);
        if (server.failToken) return json({ error: "boom" }, 500);
        return json({ access_token: `token-for-${form.username}`, token_type: "Bearer", expires_in: 3600 });
      }

      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization ?? null;
      server.calls.push({ method, url: url.pathname + url.search, body, auth });
      if (server.rejectToken && url.pathname.startsWith("/api/")) return json({ detail: "missing or invalid bearer token" }, 401);

      if (method === "GET" && url.pathname === "/api/sessions") {
        if (server.failList) return json({ detail: "boom" }, 500);
        const ids = url.searchParams.getAll("ids");
        const sessions: SessionSummary[] = ids
          .filter((id) => server.sessions.has(id))
          .map((id) => {
            const s = server.sessions.get(id)!;
            const at = new Date(Date.UTC(2026, 10, 4, 9, 0, s.lastActive)).toISOString();
            return { session_id: id, title: s.title, created_at: at, last_active_at: at, _k: s.lastActive };
          })
          .sort((a, b) => b._k - a._k)
          .map(({ _k, ...rest }) => rest);
        return json({ sessions });
      }

      const history = url.pathname.match(/^\/api\/chat\/(.+)\/history$/);
      if (method === "GET" && history) {
        if (server.failHistory) return json({ detail: "boom" }, 500);
        const id = decodeURIComponent(history[1]);
        return json({ session_id: id, messages: server.sessions.get(id)?.messages ?? [] });
      }

      if (method === "POST" && url.pathname === "/api/chat") {
        const { session_id, message: text } = body as { session_id: string; message: string };
        if (server.holdChat) await server.holdChat;
        const reply = `(mock) You said: ${text}`;
        const existing = server.sessions.get(session_id);
        const msgs = [message("user", text), message("assistant", reply)];
        if (existing) {
          existing.messages.push(...msgs);
          existing.lastActive = clock++;
        } else {
          server.sessions.set(session_id, { title: text, messages: msgs, lastActive: clock++ });
        }
        return json({ session_id, reply, intent: null, message_id: msgs[1].id });
      }

      const fb = url.pathname.match(/^\/api\/messages\/(\d+)\/feedback$/);
      if (method === "POST" && fb) {
        if (server.holdFeedback) await server.holdFeedback;
        if (server.failFeedback) return json({ detail: "boom" }, 500);
        const id = Number(fb[1]);
        const target = [...server.sessions.values()].flatMap((s) => s.messages).find((m) => m.id === id);
        if (!target) return json({ detail: "message not found" }, 404);
        if (target.role !== "assistant") return json({ detail: "feedback is only allowed on assistant messages" }, 400);
        const { rating, reason, comment } = body as { rating: string; reason?: string; comment?: string };
        server.feedback.set(id, body);
        const at = new Date(Date.UTC(2026, 10, 4, 9, 0, clock++)).toISOString();
        return json({ message_id: id, rating, reason: reason ?? null, comment: comment ?? null, trace_id: null, created_at: at, updated_at: at });
      }

      return json({ detail: "not found" }, 404);
    }),
  );

  return server;
}
