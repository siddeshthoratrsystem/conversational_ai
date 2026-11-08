// Typed calls to the backend. Each throws an Error on a network failure or a non-2xx response.
// Contract: README.md and specs/001-chat-session-sidebar/contracts/sessions-api.md.

export type ChatResponse = {
  session_id: string;
  reply: string;
  intent: string | null;
  message_id: number | null; // id of the assistant message, used for feedback (spec 002)
  education_only?: boolean | null; // spec 009: true when the access check could not be completed
};

// Who is signed in and what they may use (spec 009: specs/009-sign-in-session-access/contracts/api-auth.md).
export type Me = {
  user_id: string;
  name: string;
  access: "granted" | "denied" | "unavailable";
};

// Answer feedback (spec 002 contract: specs/002-answer-feedback/contracts/feedback-api.md).
export type FeedbackRating = "up" | "down";
export type FeedbackReason = "incorrect" | "unclear" | "wanted_a_person" | "other";
export type Feedback = { rating: FeedbackRating; reason?: FeedbackReason; comment?: string };
export type FeedbackResponse = {
  message_id: number;
  rating: FeedbackRating;
  reason: FeedbackReason | null;
  comment: string | null;
  trace_id: string | null;
  created_at: string;
  updated_at: string;
};

export type HistoryMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  intent: string | null;
  latency_ms: number | null;
  source: "agent" | "mock" | null;
  created_at: string;
};

export type HistoryResponse = { session_id: string; messages: HistoryMessage[] };

export type SessionSummary = {
  session_id: string;
  title: string;
  created_at: string;
  last_active_at: string;
};

export type SessionsResponse = { sessions: SessionSummary[] };

// The website keeps the relative path. The mobile app has no page origin, so it sets a full address.
let baseUrl = "";
// Spec 009: where the sign-in token comes from (the web sign-in, or a host app that embeds the chat).
let getToken: (() => string | null | Promise<string | null>) | undefined;
// Spec 009: called on a 401; resolve true once a fresh token is available to retry once with.
let onUnauthorized: (() => Promise<boolean>) | undefined;

/** Set the base location, token source and/or 401 handler. Only the options passed are changed. */
export function configureApi(options: {
  baseUrl?: string;
  getToken?: (() => string | null | Promise<string | null>) | undefined;
  onUnauthorized?: (() => Promise<boolean>) | undefined;
}): void {
  if (options.baseUrl !== undefined) baseUrl = options.baseUrl.replace(/\/$/, "");
  if ("getToken" in options) getToken = options.getToken;
  if ("onUnauthorized" in options) onUnauthorized = options.onUnauthorized;
}

/** A non-2xx response. `status` lets callers react to 401 and 403 (spec 009). */
export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(`Request failed (${status})`);
    this.name = "ApiError";
  }
}

async function withToken(init?: RequestInit): Promise<RequestInit | undefined> {
  const token = getToken ? await getToken() : null;
  if (!token) return init;
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res = await fetch(baseUrl + url, await withToken(init));
  if (res.status === 401 && onUnauthorized && (await onUnauthorized())) {
    res = await fetch(baseUrl + url, await withToken(init));
  }
  if (!res.ok) throw new ApiError(res.status);
  return (await res.json()) as T;
}

export function getMe(): Promise<Me> {
  return request<Me>("/api/me");
}

export function sendMessage(sessionId: string, message: string): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

// The backend replaces the whole record on each call, so always send the full desired state.
export function submitFeedback(messageId: number, feedback: Feedback): Promise<FeedbackResponse> {
  return request<FeedbackResponse>(`/api/messages/${messageId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feedback),
  });
}

export function getHistory(sessionId: string): Promise<HistoryResponse> {
  return request<HistoryResponse>(`/api/chat/${encodeURIComponent(sessionId)}/history`);
}

export async function listSessions(ids: string[]): Promise<SessionsResponse> {
  if (ids.length === 0) return { sessions: [] };
  const query = ids.map((id) => `ids=${encodeURIComponent(id)}`).join("&");
  return request<SessionsResponse>(`/api/sessions?${query}`);
}
