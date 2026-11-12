import { Check, CircleAlert, Copy, Info, Sparkles } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { parseServerTime, splitDisclaimer } from "@convai/core";
import { Button } from "@convai/ui/button";
import { cn } from "@convai/ui/cn";

import { Markdown } from "@/markdown";

const timeFormat = new Intl.DateTimeFormat(undefined, { timeStyle: "short" });

// `message`, `disclaimer` and `pending` are test hooks: keep them.

/**
 * Put `text` on the clipboard. Uses the Clipboard API, and falls back to a hidden text area where that API is
 * missing (pages not served over HTTPS or localhost, e.g. opened by the machine's network address).
 */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // denied: try the fallback
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.focus();
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

/** Copy action for a message: shows a tick and "Copied" for 2 seconds after copying. */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={copied ? "Copied" : "Copy message"}
      title={copied ? "Copied" : "Copy message"}
      onClick={async () => setCopied(await copyText(text))}
    >
      {copied ? <Check aria-hidden className="text-success-700" /> : <Copy aria-hidden />}
    </Button>
  );
}

/** Member's message (Figma "Evo / User message"): right-aligned white bubble with its time and a copy action. */
export function UserMessage({ text, time }: { text: string; time?: string }) {
  return (
    <div className="flex flex-col items-end gap-2">
      <p className="message max-w-[80%] rounded-lg bg-white px-5 py-3 text-lg whitespace-pre-wrap text-ink shadow-hairline">
        {text}
      </p>
      <div className="flex items-center gap-1 text-sm text-muted">
        {time && <time dateTime={time}>{timeFormat.format(parseServerTime(time))}</time>}
        <CopyButton text={text} />
      </div>
    </div>
  );
}

/**
 * Alfred's reply: Markdown on the page (no bubble, as in Figma), a trailing _italic_ disclaimer as a muted
 * note under it, its time (as on the member's messages), and `footer` (the feedback controls) below that.
 */
export function AssistantMessage({
  text,
  time,
  failed,
  footer,
}: {
  text: string;
  time?: string;
  failed?: boolean;
  footer?: ReactNode;
}) {
  const { body, disclaimer } = splitDisclaimer(text);
  return (
    <div className="flex flex-col gap-2.5">
      {body &&
        (failed ? (
          <p className="flex items-center gap-2 rounded-md border border-warning-100 bg-white px-4 py-3 text-base text-warning-700">
            <CircleAlert aria-hidden className="size-4 shrink-0" />
            <span className="message">{body}</span>
          </p>
        ) : (
          <div
            className={cn(
              "message text-base text-ink",
              "[&_li+li]:mt-1.5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p+p]:mt-3 [&_strong]:font-bold [&_strong]:text-navy",
              "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:marker:text-navy [&>:first-child]:mt-0 [&>:last-child]:mb-0",
            )}
          >
            <Markdown text={body} />
          </div>
        ))}
      {disclaimer && (
        <p className="flex items-start gap-1.5 text-xs text-muted">
          <Info aria-hidden className="mt-1 size-3.5 shrink-0" />
          <span className="disclaimer">{disclaimer}</span>
        </p>
      )}
      {time && (
        <time dateTime={time} className="text-sm text-muted">
          {timeFormat.format(parseServerTime(time))}
        </time>
      )}
      {footer}
    </div>
  );
}

/** Shown while Alfred is working on a reply. */
export function PendingReply() {
  return (
    <p role="status" className="pending flex items-center gap-2 text-sm text-muted">
      <Sparkles aria-hidden className="size-4 text-primary" />
      <span aria-hidden className="flex gap-1">
        {["[animation-delay:-0.3s]", "[animation-delay:-0.15s]", ""].map((delay) => (
          <span
            key={delay}
            className={cn("size-1.5 animate-bounce rounded-full bg-primary motion-reduce:animate-none", delay)}
          />
        ))}
      </span>
      <span>Alfred is thinking…</span>
      <span className="sr-only">Waiting for reply</span>
    </p>
  );
}
