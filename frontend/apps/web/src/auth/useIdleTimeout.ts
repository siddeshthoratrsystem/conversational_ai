// Idle sign-out with a warning first (spec 009 FR-008, research R4).
import { useCallback, useEffect, useRef, useState } from "react";

const ACTIVITY = ["keydown", "pointerdown", "touchstart", "focusin", "wheel"] as const;

function minutes(value: string | undefined, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export function idleSettings() {
  const timeout = minutes(import.meta.env.VITE_IDLE_TIMEOUT_MINUTES, 15);
  const warning = Math.min(minutes(import.meta.env.VITE_IDLE_WARNING_MINUTES, 2), timeout);
  return { timeoutMs: timeout * 60_000, warningMs: warning * 60_000, timeoutMinutes: timeout };
}

/** While `active`, watches for activity. Shows a warning before the timeout, then calls onTimeout. */
export function useIdleTimeout(active: boolean, onTimeout: () => void) {
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null); // null = no warning
  const lastActivity = useRef(Date.now());
  const warningOpen = useRef(false);
  const timedOut = useRef(onTimeout);
  timedOut.current = onTimeout;

  const stay = useCallback(() => {
    lastActivity.current = Date.now();
    warningOpen.current = false;
    setSecondsLeft(null);
  }, []);

  useEffect(() => {
    if (!active) return;
    const { timeoutMs, warningMs } = idleSettings();
    lastActivity.current = Date.now();

    // Activity counts until the warning shows; after that only "Stay signed in" does.
    const onActivity = () => {
      if (!warningOpen.current) lastActivity.current = Date.now();
    };
    ACTIVITY.forEach((type) => window.addEventListener(type, onActivity, { passive: true }));

    const tick = window.setInterval(() => {
      const left = timeoutMs - (Date.now() - lastActivity.current);
      if (left <= 0) {
        warningOpen.current = false;
        setSecondsLeft(null);
        timedOut.current();
      } else if (left <= warningMs) {
        warningOpen.current = true;
        setSecondsLeft(Math.ceil(left / 1000));
      }
    }, 1000);

    return () => {
      ACTIVITY.forEach((type) => window.removeEventListener(type, onActivity));
      window.clearInterval(tick);
      warningOpen.current = false;
      setSecondsLeft(null);
    };
  }, [active]);

  return { secondsLeft, stay };
}
