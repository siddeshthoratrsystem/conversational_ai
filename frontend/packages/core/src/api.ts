// Typed calls to the backend. Each throws an Error on a network failure or a non-2xx response.
// Contract: README.md and specs/001-chat-session-sidebar/contracts/sessions-api.md.

export type ChatResponse = {
  session_id: string;
  reply: string;
  intent: string | null;
  message_id: number | null; // id of the assistant message, used for feedback (spec 002)
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
  source: "agent" | "mock" | "gate" | null;
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
let getToken: () => string | null = () => null;
let onUnauthorized: () => void = () => {};

// Each option is optional; only the ones given are changed.
export function configureApi(options: {
  baseUrl?: string;
  /** Supplies the access token, read on every request (spec 008). */
  getToken?: () => string | null;
  /** Called once on any 401, before the call throws (spec 008). */
  onUnauthorized?: () => void;
}): void {
  if (options.baseUrl !== undefined) baseUrl = options.baseUrl.replace(/\/$/, "");
  if (options.getToken) getToken = options.getToken;
  if (options.onUnauthorized) onUnauthorized = options.onUnauthorized;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const withAuth = token
    ? { ...init, headers: { ...(init?.headers as Record<string, string> | undefined), Authorization: `Bearer ${token}` } }
    : init;
  const res = await fetch(baseUrl + url, withAuth);
  if (res.status === 401) onUnauthorized();
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as T;
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
