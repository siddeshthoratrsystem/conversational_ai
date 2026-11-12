import { CircleAlert, CornerDownLeft, X } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";

import { cn } from "@convai/ui/cn";
import { Soundwave } from "@convai/ui/soundwave";

import { AttachButton, AttachmentCard, type Attachment } from "./Attach";

/**
 * Alfred's message box (Figma "AI / Composer") with the disclosure line under it.
 * Enter, or the Enter arrow button, sends; Shift+Enter adds a new line (spec 003 FR-004). The box grows with its text.
 * + attaches a file (spec 016); it is shown here but not sent until the upload service exists (backlog BL-032), and
 * sending a message clears it.
 * `listening` is the guided tour's voice step: the voice button shows the X that ends a voice conversation.
 */
export function Composer({
  value,
  onChange,
  onSend,
  busy,
  listening = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /** A reply is pending: Send is disabled. */
  busy: boolean;
  listening?: boolean;
}) {
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    // Sending clears the attachment: files aren't sent yet (backlog BL-032), and keeping the file around suggested
    // it would go with the next message. An empty message sends nothing, so the file stays.
    if (value.trim() && !busy) {
      setAttachment(null);
      setAttachError(null);
    }
    onSend();
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!busy) e.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <div className="relative flex flex-col items-center gap-2.5 pb-4">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 -top-14 h-14 bg-linear-to-b from-page/0 to-page" />
      {attachError && (
        <p role="alert" className="flex items-center gap-1.5 self-start text-sm text-danger-700">
          <CircleAlert aria-hidden className="size-4 shrink-0" />
          {attachError}
        </p>
      )}
      <form
        onSubmit={submit}
        className={cn(
          "relative flex w-full flex-col gap-3 border-[1.5px] border-accent bg-white py-2 pr-2 pl-1.5 shadow-glow focus-within:border-primary-strong",
          attachment ? "rounded-3xl" : "rounded-2xl",
        )}
      >
        {attachment && (
          <div className="flex flex-col items-start gap-1.5">
            <AttachmentCard file={attachment} onRemove={() => setAttachment(null)} />
            <p className="px-1 text-xs text-muted">Sending files is coming soon: only your message will be sent.</p>
          </div>
        )}
        <div className="flex min-h-8 items-end gap-2">
          <AttachButton attached={attachment !== null} onAttach={setAttachment} onError={setAttachError} />
          <textarea
            aria-label="Message Alfred"
            placeholder={attachment ? "Ask about this document…" : "Ask anything about your money…"}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            className="field-sizing-content max-h-40 min-h-8 min-w-0 flex-1 resize-none bg-transparent py-1 text-base text-ink outline-none placeholder:text-muted"
          />
          <button
            type="submit"
            aria-label="Send message"
            title="Send (Enter)"
            disabled={busy}
            className="grid size-8 shrink-0 place-items-center rounded-full text-subtle transition-colors hover:bg-info-100 hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
          >
            <CornerDownLeft aria-hidden className="size-4" />
          </button>
          <button
            type="submit"
            data-tour="voice"
            aria-label={listening ? "End voice" : "Send"}
            disabled={busy}
            className="grid size-8 shrink-0 place-items-center rounded-full bg-ai text-white transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {listening ? <X aria-hidden className="size-4" /> : <Soundwave className="size-4" />}
          </button>
        </div>
      </form>
      <p className="text-center text-sm text-muted">AI-generated from demo data and can be wrong. Not financial advice.</p>
    </div>
  );
}
