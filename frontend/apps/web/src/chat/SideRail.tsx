import { Bell, History, List, MessageSquarePlus, type LucideIcon } from "lucide-react";
import type { ComponentProps, Ref } from "react";

import { cn } from "@convai/ui/cn";

function RailButton({
  icon: Icon,
  label,
  active,
  className,
  ...props
}: ComponentProps<"button"> & { icon: LucideIcon; label: string; active?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "grid size-9 place-items-center rounded-md text-ink hover:bg-info-75 focus-visible:outline-2 focus-visible:outline-primary",
        "disabled:cursor-not-allowed disabled:text-subtle disabled:hover:bg-transparent",
        active && "bg-info-100 text-navy hover:bg-info-100",
        className,
      )}
      {...props}
    >
      <Icon aria-hidden className="size-5" strokeWidth={1.75} />
    </button>
  );
}

/** Alfred's left icon rail (Figma A9). Tasks opens the Guided tasks overlay and keeps it open (spec 010); Notifications isn't built yet. */
export function SideRail({
  historyOpen,
  onToggleHistory,
  tasksOpen,
  onOpenTasks,
  tasksButtonRef,
  onNewChat,
  initial,
}: {
  historyOpen: boolean;
  onToggleHistory: () => void;
  tasksOpen: boolean;
  onOpenTasks: () => void;
  tasksButtonRef?: Ref<HTMLButtonElement>;
  onNewChat: () => void;
  initial: string;
}) {
  return (
    <nav
      aria-label="Alfred"
      className="z-30 flex w-12.5 shrink-0 flex-col items-center gap-2 border-r border-line bg-white pt-5 pb-6"
    >
      {/* Figma order: Chat, Tasks, History, Notifications. "Chat" starts a new conversation. */}
      <RailButton icon={MessageSquarePlus} label="New chat" onClick={onNewChat} />
      <RailButton
        ref={tasksButtonRef}
        icon={List}
        label="Tasks"
        active={tasksOpen}
        aria-expanded={tasksOpen}
        aria-controls="guided-tasks"
        onClick={onOpenTasks}
      />
      <RailButton
        icon={History}
        label="History"
        active={historyOpen}
        aria-expanded={historyOpen}
        aria-controls="chat-history"
        onClick={onToggleHistory}
      />
      <RailButton icon={Bell} label="Notifications (coming soon)" disabled />
      <span
        aria-hidden
        className="mt-auto grid size-9 place-items-center rounded-full bg-info-100 text-base font-bold text-navy"
      >
        {initial}
      </span>
    </nav>
  );
}
