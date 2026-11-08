// Where to pick up after an inactivity sign-out or a lost session (spec 009 FR-009, research R4).
// Kept in this tab only (sessionStorage); holds the open chat id and the unsent text, never tokens.

const KEY = "convai.resume";

export type Resume = { sessionId: string | null; draft: string };

export function saveResume(resume: Resume): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(resume));
  } catch {
    // Storage blocked: the customer just starts fresh.
  }
}

/** Read the saved state once and remove it. Anything unreadable is ignored. */
export function takeResume(): Resume | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    if (raw === null) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return null;
    const { sessionId, draft } = value as Record<string, unknown>;
    return {
      sessionId: typeof sessionId === "string" && sessionId ? sessionId : null,
      draft: typeof draft === "string" ? draft : "",
    };
  } catch {
    return null;
  }
}

export function clearResume(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing to clear
  }
}
