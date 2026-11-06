import { useEffect, useRef, type KeyboardEvent } from "react";

import { Button } from "@convai/ui/button";
import { Card } from "@convai/ui/card";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** "Are you still there?" (spec 009 FR-008). Focus stays inside; Escape means stay. */
export function IdleWarning({
  secondsLeft,
  onStay,
  onSignOut,
}: {
  secondsLeft: number;
  onStay: () => void;
  onSignOut: () => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    dialog.current?.querySelector<HTMLButtonElement>("[data-stay]")?.focus();
  }, []);

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onStay();
    } else if (e.key === "Tab") {
      const buttons = Array.from(dialog.current?.querySelectorAll("button") ?? []);
      const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next = e.shiftKey ? (i <= 0 ? buttons.length - 1 : i - 1) : (i + 1) % buttons.length;
      e.preventDefault();
      buttons[next]?.focus();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/40 px-6">
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="idle-title"
        aria-describedby="idle-text"
        onKeyDown={onKeyDown}
        className="w-full max-w-100"
      >
        <Card variant="tile" className="flex flex-col gap-4 p-6">
          <h2 id="idle-title" className="text-xl font-bold text-navy">
            Are you still there?
          </h2>
          <p id="idle-text" className="text-base text-ink" aria-live="polite">
            You'll be signed out in {clock(secondsLeft)}.
          </p>
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="secondary" onClick={onSignOut}>
              Sign out
            </Button>
            <Button data-stay variant="primary" onClick={onStay}>
              Stay signed in
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
