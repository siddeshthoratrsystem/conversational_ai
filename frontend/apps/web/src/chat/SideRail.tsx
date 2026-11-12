import { History, List, MessageSquare, type LucideIcon } from "lucide-react";
import type { ComponentProps, Ref } from "react";

import { cn } from "@convai/ui/cn";
import { PrincipalMark } from "@convai/ui/logo";

/** A labelled rail tab (Figma "Nav / Chat", "Nav / Tasks"): icon over label, light blue box when selected or hovered. */
function RailTab({
  icon: Icon,
  label,
  selected,
  className,
  ...props
}: ComponentProps<"button"> & { icon: LucideIcon; label: string; selected?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        "flex min-w-14 flex-col items-center rounded-md px-3 pt-2 pb-1 text-sm font-bold text-navy transition-colors",
        "hover:bg-info-100 focus-visible:outline-2 focus-visible:outline-primary",
        selected && "bg-info-100",
        className,
      )}
      {...props}
    >
      <Icon aria-hidden className="size-5 text-primary" strokeWidth={1.75} />
      {label}
    </button>
  );
}

/**
 * Alfred's left rail (Figma "AI / Side rail"), shown on every page after the homepage (spec 016). The logo starts
 * a new chat, which returns to the homepage. History isn't in the design; it stays so past chats remain reachable.
 */
export function SideRail({
  historyOpen,
  onToggleHistory,
  tasksOpen,
  onOpenTasks,
  onShowChat,
  tasksButtonRef,
  onNewChat,
  initial,
}: {
  historyOpen: boolean;
  onToggleHistory: () => void;
  tasksOpen: boolean;
  onOpenTasks: () => void;
  /** Back to the conversation (closes the Guided tasks page). */
  onShowChat: () => void;
  tasksButtonRef?: Ref<HTMLButtonElement>;
  onNewChat: () => void;
  initial: string;
}) {
  return (
    <nav
      aria-label="Alfred"
      className="z-30 flex w-21 shrink-0 flex-col items-center gap-2 border-r-[0.5px] border-line bg-white px-3 pt-5 pb-6"
    >
      <button
        type="button"
        aria-label="New chat"
        title="New chat"
        onClick={onNewChat}
        className="grid place-items-center rounded-md p-1 transition-colors hover:bg-info-100 focus-visible:outline-2 focus-visible:outline-primary"
      >
        <PrincipalMark />
      </button>
      <span aria-hidden className="h-4" />
      <RailTab
        icon={MessageSquare}
        label="Chat"
        selected={!tasksOpen}
        aria-current={tasksOpen ? undefined : "page"}
        onClick={onShowChat}
      />
      <RailTab
        ref={tasksButtonRef}
        icon={List}
        label="Tasks"
        selected={tasksOpen}
        aria-expanded={tasksOpen}
        aria-controls="guided-tasks"
        onClick={onOpenTasks}
      />
      <RailTab
        icon={History}
        label="History"
        selected={historyOpen}
        aria-expanded={historyOpen}
        aria-controls="chat-history"
        onClick={onToggleHistory}
      />
      <span
        aria-hidden
        className="mt-auto grid size-9 place-items-center rounded-full bg-info-100 text-base font-bold text-navy"
      >
        {initial}
      </span>
    </nav>
  );
}
