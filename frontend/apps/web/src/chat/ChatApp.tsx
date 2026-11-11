import { useCallback, useEffect, useRef, useState } from "react";

import { getHistory, listSessions, sendMessage, submitFeedback, type Feedback, type SessionSummary } from "@convai/core";
import type { User } from "@/auth/user";
import { cn } from "@convai/ui/cn";
import { getSessionIds, rememberSession } from "@/sessionStore";
import { AlfredHeader } from "./AlfredHeader";
import { Composer } from "./Composer";
import FeedbackBar, { type FeedbackState } from "./FeedbackBar";
import { GuidedTasks } from "./GuidedTasks";
import { HistoryPanel } from "./HistoryPanel";
import { AssistantMessage, PendingReply, UserMessage } from "./Messages";
import { SideRail } from "./SideRail";
import { Welcome } from "./Welcome";

// `failed` marks the "Something went wrong." reply so it gets the error style (view only, never sent).
// `id` is the backend message id; replies with one can be rated (spec 004). `time` is an ISO timestamp.
type Message = { id?: number; role: "user" | "assistant"; text: string; time?: string; failed?: boolean };
type HistoryError = { message: string; retry: () => void };

/** Narrow screens show History as an overlay, so picking a chat closes it there. */
const isNarrow = () => window.matchMedia?.("(max-width: 767px)").matches ?? false;

/** Full-page Alfred (Figma A9): header, icon rail, optional History panel, and the conversation. */
export function ChatApp({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [activeSessionId, setActiveSessionId] = useState<string>(() => crypto.randomUUID());
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Set<string>>(() => new Set()); // sessions awaiting a reply
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [historyError, setHistoryError] = useState<HistoryError | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  // The Guided tasks overlay covers the chat, which stays mounted so nothing is lost (spec 010 FR-009).
  const [tasksOpen, setTasksOpen] = useState(false);
  const tasksButton = useRef<HTMLButtonElement>(null);
  // Feedback per assistant message id, kept for this visit across chat switches (spec 004 FR-011).
  const [feedback, setFeedback] = useState<Map<number, FeedbackState>>(() => new Map());
  const savingFeedback = useRef<Set<number>>(new Set()); // one save per reply at a time (FR-010)
  const end = useRef<HTMLDivElement>(null);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const { sessions } = await listSessions(getSessionIds());
      setSessions(sessions);
      setHistoryError(null);
    } catch {
      setHistoryError({ message: "Couldn't load past chats.", retry: () => void loadSessions() });
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  // Which conversation is on screen, and a counter bumped each time the view changes.
  // Async results (replies, history loads) check these so they never land in the wrong chat.
  const activeRef = useRef(activeSessionId);
  const viewVersion = useRef(0);
  const openRequest = useRef(0);

  const showSession = useCallback((sessionId: string, msgs: Message[]) => {
    activeRef.current = sessionId;
    viewVersion.current += 1;
    setActiveSessionId(sessionId);
    setMessages(msgs);
  }, []);

  const openSession = useCallback(
    async (sessionId: string) => {
      const request = ++openRequest.current;
      try {
        const history = await getHistory(sessionId);
        if (request !== openRequest.current) return; // a newer selection won
        // Only switch once the history is in, so a failure leaves the current chat untouched.
        showSession(
          sessionId,
          history.messages.map((m) => ({ id: m.id, role: m.role, text: m.content, time: m.created_at })),
        );
        setHistoryError(null);
        setTasksOpen(false);
        if (isNarrow()) setHistoryOpen(false);
      } catch {
        if (request !== openRequest.current) return;
        setHistoryError({ message: "Couldn't open that chat.", retry: () => void openSession(sessionId) });
      }
    },
    [showSession],
  );

  function newChat() {
    // A fresh id only; nothing is stored or sent until the first message (spec FR-008).
    openRequest.current += 1; // drop any history load still in flight
    showSession(crypto.randomUUID(), []);
    setHistoryError(null);
    setInput("");
    setTasksOpen(false);
    if (isNarrow()) setHistoryOpen(false);
  }

  // Escape closes the overlay and hands focus back to the button that opened it (spec 010 FR-008).
  useEffect(() => {
    if (!tasksOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setTasksOpen(false);
      tasksButton.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [tasksOpen]);

  async function sendText(raw: string) {
    const text = raw.trim();
    if (!text || pending.has(activeSessionId)) return;
    const sessionId = activeSessionId;
    const version = viewVersion.current;
    setMessages((m) => [...m, { role: "user", text, time: new Date().toISOString() }]);
    setInput("");
    setPending((p) => new Set(p).add(sessionId));

    let reply: string;
    let replyId: number | undefined;
    let ok = false;
    try {
      const res = await sendMessage(sessionId, text);
      reply = res.reply;
      replyId = typeof res.message_id === "number" ? res.message_id : undefined;
      ok = true;
    } catch {
      reply = "Something went wrong.";
    } finally {
      setPending((p) => {
        const next = new Set(p);
        next.delete(sessionId);
        return next;
      });
    }

    if (ok) {
      rememberSession(sessionId);
      void loadSessions();
    }
    if (viewVersion.current === version) {
      setMessages((m) => [...m, { id: replyId, role: "assistant", text: reply, failed: !ok }]);
    } else if (ok && activeRef.current === sessionId) {
      // The user left and came back while waiting; the server has the full thread now.
      void openSession(sessionId);
    }
  }

  const waiting = pending.has(activeSessionId);
  const showWelcome = messages.length === 0 && !waiting;

  // Keep the newest message in view (not on the welcome screen, which should start at its greeting).
  useEffect(() => {
    if (messages.length > 0 || waiting) end.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, waiting]);

  function updateFeedback(messageId: number, change: Partial<FeedbackState>) {
    setFeedback((all) => {
      const next = new Map(all);
      const current = next.get(messageId) ?? { saved: null, saving: false, error: null };
      next.set(messageId, { ...current, ...change });
      return next;
    });
  }

  // The screen shows only what the backend confirmed (SC-003); a failure keeps the last saved state.
  async function saveFeedback(messageId: number, value: Feedback) {
    if (savingFeedback.current.has(messageId)) return;
    savingFeedback.current.add(messageId);
    updateFeedback(messageId, { saving: true });
    try {
      await submitFeedback(messageId, value);
      updateFeedback(messageId, { saved: value, saving: false, error: null });
    } catch {
      updateFeedback(messageId, { saving: false, error: { attempted: value } });
    } finally {
      savingFeedback.current.delete(messageId);
    }
  }

  return (
    // `layout`/`open` and `backdrop` are test hooks: keep them.
    <div className={cn("layout flex h-dvh flex-col bg-page text-ink", historyOpen && "open")}>
      <AlfredHeader user={user} onSignOut={onSignOut} />
      <div className="relative flex min-h-0 flex-1">
        <SideRail
          historyOpen={historyOpen}
          onToggleHistory={() => setHistoryOpen((o) => !o)}
          tasksOpen={tasksOpen}
          onOpenTasks={() => setTasksOpen(true)}
          tasksButtonRef={tasksButton}
          onNewChat={newChat}
          initial={user.displayName[0]}
        />
        {historyOpen && (
          <>
            <div
              aria-hidden="true"
              className="backdrop fixed inset-0 top-14.5 left-12.5 z-20 bg-navy/30 md:hidden"
              onClick={() => setHistoryOpen(false)}
            />
            <aside
              id="chat-history"
              className="fixed top-14.5 bottom-0 left-12.5 z-30 w-72 overflow-y-auto border-r border-line bg-white shadow-float md:static md:z-0 md:shadow-none"
            >
              <HistoryPanel
                sessions={sessions}
                activeSessionId={activeSessionId}
                onSelect={(id) => void openSession(id)}
                error={historyError?.message ?? null}
                onRetry={() => historyError?.retry()}
                loading={sessionsLoading}
              />
            </aside>
          </>
        )}
        {/* A history error shows in the panel when it's open, and here otherwise. */}
        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Soft blue glow at the top of the chat (Figma "Aura glow") and a fade under the header. */}
          <div
            aria-hidden
            className="pointer-events-none absolute -top-114 left-1/2 h-185.75 w-321.5 -translate-x-1/2 bg-aura opacity-20"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 z-10 h-10 bg-linear-to-b from-page to-page/0"
          />
          {/* The bottom padding keeps the last message clear of the composer's fade. The welcome gets a wider
              column and is centred in the space left (auto margins, so it still scrolls from the top when it can't fit). */}
          <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto px-6 pt-6 pb-16">
            <div
              role="log"
              aria-label="Conversation with Alfred"
              className={cn("mx-auto flex w-full flex-col gap-6", showWelcome ? "my-auto max-w-250" : "max-w-190")}
            >
              {historyError && !historyOpen && (
                <div
                  role="alert"
                  className="flex items-center justify-between gap-2 rounded-md bg-warning-100 px-4 py-2 text-sm text-warning-700"
                >
                  <span>{historyError.message}</span>
                  <button type="button" className="font-bold underline" onClick={() => historyError.retry()}>
                    Retry
                  </button>
                </div>
              )}
              {showWelcome && <Welcome name={user.displayName} onAsk={(q) => void sendText(q)} />}
              {messages.map((m, i) =>
                m.role === "user" ? (
                  <UserMessage key={`${activeSessionId}-${i}`} text={m.text} time={m.time} />
                ) : (
                  <AssistantMessage
                    key={`${activeSessionId}-${i}`}
                    text={m.text}
                    failed={m.failed}
                    footer={
                      m.id !== undefined && (
                        <FeedbackBar
                          state={feedback.get(m.id)}
                          onSubmit={(value) => void saveFeedback(m.id!, value)}
                          onRetry={() => {
                            const attempted = feedback.get(m.id!)?.error?.attempted;
                            if (attempted) void saveFeedback(m.id!, attempted);
                          }}
                        />
                      )
                    }
                  />
                ),
              )}
              {waiting && <PendingReply />}
              <div ref={end} />
            </div>
          </div>
          <div className="relative mx-auto w-full max-w-200 px-6">
            <Composer value={input} onChange={setInput} onSend={() => void sendText(input)} busy={waiting} />
          </div>
          {tasksOpen && <GuidedTasks />}
        </main>
      </div>
    </div>
  );
}
