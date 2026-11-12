import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { cn } from "@convai/ui/cn";

/** Where a step points: the element marked `data-tour="<target>"`, with the ring's padding and shape around it. */
type Spot = { target: string; padX: number; padY: number; round: "full" | "card"; place: "below" | "above"; align?: "end" };

/** `reveal` is another `data-tour` element the step scrolls into view (the listening flock). */
export type TourStep = { text: string; spot?: Spot; wide?: boolean; tapTarget?: boolean; reveal?: string };

// Figma "Flow / Guided tour" 1–7, copy as designed except the assistant's name: the design says Eddie, the app is
// Alfred everywhere else, so the tour says Alfred until the name is settled.
export const TOUR_STEPS: TourStep[] = [
  {
    text: "Hi, I'm Alfred, your AI financial assistant. Let me show you quickly how this works.",
    spot: { target: "brand", padX: 12, padY: 8, round: "full", place: "below" },
  },
  {
    text: "These cards are your starting points — each one is a goal I can take you through, end to end. Tap any to dive in.",
    spot: { target: "cards", padX: 12, padY: 12, round: "card", place: "below" },
    wide: true,
  },
  {
    text: "You can type to me, or tap here to just talk instead — it works exactly the same way. Go ahead and tap it.",
    spot: { target: "voice", padX: 8, padY: 8, round: "full", place: "above" },
    tapTarget: true,
  },
  {
    text: "Try saying something, then tap here again to end the conversation when you're done.",
    spot: { target: "voice", padX: 8, padY: 8, round: "full", place: "above" },
    tapTarget: true,
    reveal: "flock",
  },
  {
    text: "Beyond answering questions, I can also take care of things for you in the background. Tap here to see what’s possible.",
    spot: { target: "automations", padX: 6, padY: 6, round: "card", place: "below", align: "end" },
    wide: true,
  },
  {
    text: "Here you’ll find things I can set up to run automatically — like a monthly spend report or flagging a cash shortfall early — without having to ask in chat each time.",
    spot: { target: "tasks-title", padX: 16, padY: 13, round: "full", place: "below" },
  },
  { text: "That's the tour. Ask me anything in the chat, or tap a card to begin — I'm here whenever you need me." },
];

/** Step 4 (index 3) shows the listening state; steps 6 and 7 are on the Guided tasks page. */
export const LISTENING_STEP = 3;
export const TASKS_STEP = 5;

const MARGIN = 12; // keeps the callout off the window edges
const GAP = 14; // between the ring and the callout
const ARROW_INSET = 24; // the pointer stays this far from the callout's corners

type Box = { top: number; left: number; width: number; height: number };
type Layout = { ring: Box | null; callout: { top: number; left: number }; arrow: { left: number; side: "top" | "bottom" } | null };

function measure(step: TourStep, callout: HTMLElement | null): Layout {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = callout?.offsetWidth ?? 0;
  const height = callout?.offsetHeight ?? 0;
  const el = step.spot && document.querySelector<HTMLElement>(`[data-tour="${step.spot.target}"]`);
  if (!step.spot || !el) {
    return { ring: null, callout: { top: Math.max(MARGIN, (vh - height) / 2), left: Math.max(MARGIN, (vw - width) / 2) }, arrow: null };
  }
  const r = el.getBoundingClientRect();
  const { padX, padY, place, align } = step.spot;
  const ring = { top: r.top - padY, left: r.left - padX, width: r.width + 2 * padX, height: r.height + 2 * padY };
  const centre = ring.left + ring.width / 2;

  const wanted = align === "end" ? ring.left + ring.width - width : centre - width / 2;
  const left = Math.min(Math.max(wanted, MARGIN), Math.max(MARGIN, vw - width - MARGIN));
  // Below or above as designed, flipping when that side has no room.
  const below = ring.top + ring.height + GAP;
  const above = ring.top - GAP - height;
  const fitsBelow = below + height <= vh - MARGIN;
  const fitsAbove = above >= MARGIN;
  const side = place === "below" ? (fitsBelow || !fitsAbove ? "below" : "above") : fitsAbove || !fitsBelow ? "above" : "below";
  const top = side === "below" ? below : above;
  const arrowLeft = Math.min(Math.max(centre - left, ARROW_INSET), Math.max(ARROW_INSET, width - ARROW_INSET));
  return { ring, callout: { top, left }, arrow: { left: arrowLeft, side: side === "below" ? "top" : "bottom" } };
}

/**
 * The guided tour over the homepage (Figma "Flow / Guided tour"): a dimmed page with a ring around the element the
 * step is about, and a callout with the step count, the text, Skip tour and Next (Done on the last step).
 * The page under the scrim can't be used; on the voice steps the ringed button can be tapped to go on.
 * Escape skips the tour.
 */
export function Tour({ step, onNext, onSkip }: { step: number; onNext: () => void; onSkip: () => void }) {
  const current = TOUR_STEPS[step];
  const last = step === TOUR_STEPS.length - 1;
  const callout = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const [layout, setLayout] = useState<Layout | null>(null);

  const place = useCallback(() => setLayout(measure(current, callout.current)), [current]);

  // Bring the target into view, then place the ring and callout; again whenever the page moves or resizes.
  useLayoutEffect(() => {
    for (const target of [current.spot?.target, current.reveal]) {
      if (target) document.querySelector(`[data-tour="${target}"]`)?.scrollIntoView?.({ block: "nearest" });
    }
    place();
    const frame = requestAnimationFrame(place); // after anything the step opened (the Guided tasks page) has laid out
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [current, place]);

  // Focus Next once the callout is placed (it is hidden until then, and hidden elements can't take focus).
  const placed = layout !== null;
  useEffect(() => {
    if (placed) next.current?.focus();
  }, [step, placed]);

  // Capture phase on window, so Escape ends the tour without also closing the Guided tasks page under it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onSkip();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onSkip]);

  // Tab stays on the callout's two buttons.
  function trapTab(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab") return;
    const buttons = callout.current?.querySelectorAll<HTMLButtonElement>("button");
    if (!buttons || buttons.length === 0) return;
    const first = buttons[0];
    const lastButton = buttons[buttons.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      lastButton.focus();
    } else if (!e.shiftKey && document.activeElement === lastButton) {
      e.preventDefault();
      first.focus();
    }
  }

  const ring = layout?.ring;
  const rounded = current.spot?.round === "card" ? "rounded-3xl" : "rounded-full";

  return (
    <div className="fixed inset-0 z-50">
      {/* Blocks the page; the ring's own shadow does the dimming, so with no ring the whole page is dimmed here. */}
      <div aria-hidden className={cn("absolute inset-0", !ring && "bg-navy/22")} />
      {ring && (
        <div
          aria-hidden
          data-tour-ring
          className={cn("pointer-events-none absolute border-2 border-primary shadow-spotlight", rounded)}
          style={{ top: ring.top, left: ring.left, width: ring.width, height: ring.height }}
        />
      )}
      {ring && current.tapTarget && (
        // "Go ahead and tap it": the ringed voice button moves the tour on. Next does the same for keyboards.
        <button
          type="button"
          tabIndex={-1}
          aria-hidden
          onClick={onNext}
          className={cn("absolute cursor-pointer", rounded)}
          style={{ top: ring.top, left: ring.left, width: ring.width, height: ring.height }}
        />
      )}
      <div
        ref={callout}
        role="dialog"
        aria-modal="true"
        aria-label="Guided tour"
        aria-describedby="tour-text"
        onKeyDown={trapTab}
        className={cn(
          "absolute flex max-w-[calc(100vw-24px)] flex-col gap-2 rounded-3xl bg-white px-4 pt-4 pb-3.5 shadow-hairline",
          current.wide ? "w-105" : "w-69",
          !layout && "invisible",
        )}
        style={layout?.callout}
      >
        {layout?.arrow && (
          <span
            aria-hidden
            className={cn(
              "absolute size-3.5 -translate-x-1/2 rotate-45 bg-white",
              layout.arrow.side === "top" ? "-top-1.75" : "-bottom-1.75",
            )}
            style={{ left: layout.arrow.left }}
          />
        )}
        <p className="text-sm font-bold text-muted">
          {step + 1} / {TOUR_STEPS.length}
        </p>
        <p id="tour-text" className="text-sm text-ink">
          {current.text}
        </p>
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={onSkip}
            className="rounded-sm text-sm font-bold text-muted hover:text-navy focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Skip tour
          </button>
          <button
            ref={next}
            type="button"
            onClick={onNext}
            className="h-9 rounded-full bg-ai px-4 text-sm font-bold text-white shadow-lift ring-[1.5px] ring-info-400 ring-inset transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
