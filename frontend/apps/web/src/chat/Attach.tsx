import { File as FileIcon, FileText, Paperclip, Plus, Upload, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { cn } from "@convai/ui/cn";

// The attach screens (Figma "A0 — Attach menu", "A3 — Document attached"). Files are picked and checked here but not
// sent: there is no upload service yet (backlog BL-032), so the composer says so and sends the text alone.

const TYPES: Record<string, string> = { "application/pdf": "PDF", "image/jpeg": "JPG", "image/png": "PNG" };
const MAX_BYTES = 10 * 1024 * 1024;

export type Attachment = { name: string; kind: string; size: number };

/** The file as an attachment, or why it is refused. */
function check(file: File): Attachment | string {
  const kind = TYPES[file.type];
  if (!kind) return `${file.name} can’t be attached. Use a PDF, JPG or PNG.`;
  if (file.size > MAX_BYTES) return `${file.name} is over 10 MB.`;
  return { name: file.name, kind, size: file.size };
}

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${Number(mb.toFixed(1))} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function MenuOption({
  icon: Icon,
  title,
  detail,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-info-50 focus-visible:outline-2 focus-visible:outline-primary"
    >
      <span aria-hidden className="grid size-8.5 shrink-0 place-items-center rounded-lg bg-info-100 text-ink">
        <Icon className="size-4.5" />
      </span>
      <span className="flex flex-col">
        <span className="text-sm font-bold text-navy">{title}</span>
        <span className="text-sm text-muted">{detail}</span>
      </span>
    </button>
  );
}

/**
 * The composer's + button and its "Add to the conversation" menu. Picks one file from the device or the camera,
 * checks it (PDF, JPG or PNG, up to 10 MB) and reports it, or why it was refused, to the composer.
 */
export function AttachButton({
  attached,
  onAttach,
  onError,
}: {
  attached: boolean;
  onAttach: (file: Attachment) => void;
  onError: (message: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const device = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  function choose(input: HTMLInputElement | null) {
    setOpen(false);
    input?.click();
  }

  function picked(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // picking the same file again still fires change
    if (!file) return;
    const result = check(file);
    if (typeof result === "string") onError(result);
    else {
      onError(null);
      onAttach(result);
    }
  }

  return (
    <div ref={root} className="relative shrink-0">
      <button
        ref={button}
        type="button"
        aria-label="Add to the conversation"
        aria-expanded={open}
        aria-controls="attach-menu"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "grid size-8 place-items-center rounded-full text-ink transition-colors hover:bg-info-100",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
          open && "bg-info-100",
        )}
      >
        {attached ? <Paperclip aria-hidden className="size-4" /> : <Plus aria-hidden className="size-4" />}
      </button>
      <input ref={device} type="file" hidden data-source="device" accept={Object.keys(TYPES).join(",")} onChange={picked} />
      <input
        ref={camera}
        type="file"
        hidden
        data-source="camera"
        accept="image/jpeg,image/png"
        capture="environment"
        onChange={picked}
      />
      {open && (
        <div
          id="attach-menu"
          role="group"
          aria-labelledby="attach-menu-title"
          className="absolute bottom-full left-0 z-30 mb-3 flex w-85 max-w-[calc(100vw-2rem)] flex-col gap-0.5 rounded-lg border border-line bg-white p-2 shadow-dropdown"
        >
          <div className="flex flex-col gap-0.5 px-3 py-2">
            <p id="attach-menu-title" className="text-base font-bold text-navy">
              Add to the conversation
            </p>
            <p className="text-sm text-muted">I’ll read it and use it in my answers.</p>
          </div>
          <MenuOption
            icon={Upload}
            title="Upload from device"
            detail="PDF, JPG or PNG, up to 10 MB"
            onClick={() => choose(device.current)}
          />
          <MenuOption
            icon={FileIcon}
            title="Take a photo"
            detail="Snap a pay stub or statement"
            onClick={() => choose(camera.current)}
          />
          <hr className="border-line" />
          <p className="px-3 pt-2.5 pb-1.5 text-sm text-muted">Files stay private to your account</p>
        </div>
      )}
    </div>
  );
}

/** The attached file inside the message box (Figma "Attachment"), with a remove button. */
export function AttachmentCard({ file, onRemove }: { file: Attachment; onRemove: () => void }) {
  return (
    <div
      role="group"
      aria-label="Attached file"
      className="flex max-w-full items-center gap-3 rounded-lg border border-line bg-page py-2 pr-3 pl-2"
    >
      <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-lg bg-ai text-white">
        <FileText className="size-5" />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-bold text-navy">{file.name}</span>
        <span className="text-sm text-muted">
          {file.kind} · {formatSize(file.size)} · ready
        </span>
      </span>
      <button
        type="button"
        aria-label={`Remove ${file.name}`}
        onClick={onRemove}
        className="ml-2 grid size-6 shrink-0 place-items-center rounded-full text-ink transition-colors hover:bg-white focus-visible:outline-2 focus-visible:outline-primary"
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
