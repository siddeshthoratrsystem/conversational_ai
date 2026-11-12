import { ChartLine, Sprout, TrendingDown, Zap, type LucideIcon } from "lucide-react";

import { AiButton } from "@convai/ui/ai-button";

import { Flock } from "./Flock";

type Starter = {
  icon: LucideIcon;
  title: string;
  body: string;
  /** The button's label and the message it sends. */
  action: { label: string; prompt: string };
};

// Figma "AI / Starter" cards (spec 016 FR-003), copy as designed. The prompts are ours: the design doesn't say.
export const STARTERS: Starter[] = [
  {
    icon: ChartLine,
    title: "You’re $500K short of your retirement goal",
    body: "Increasing your 401(k) contribution by $220 a month closes that gap by retirement.",
    action: { label: "Close the gap", prompt: "How can I close the $500K gap in my retirement savings?" },
  },
  {
    icon: Sprout,
    title: "Your Chase savings has $3,200 earning nothing",
    body: "There's likely a better place for that money to sit, want to see?",
    action: { label: "Tell me more", prompt: "Where could the $3,200 in my Chase savings earn more?" },
  },
  {
    icon: TrendingDown,
    title: "Pay off your debt faster than you think",
    body: "I'll build a personalized payoff plan that fits your monthly budget.",
    action: { label: "Build my plan", prompt: "Build me a plan to pay off my debt faster." },
  },
  {
    icon: Zap,
    title: "Put your finances on autopilot",
    body: "I can watch for overspending, send a monthly spend report, and more, without you having to ask.",
    action: { label: "Explore automations", prompt: "What could you automate for my finances?" },
  },
];

export function greetingFor(date: Date): string {
  const hour = date.getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/**
 * Empty chat (Figma "L4 — Search bar — C — Glow + stroke"): visual, greeting, plan update and starter cards.
 * The cards go 1 → 2 → 4 across with the space this section gets (a container query, so the History panel
 * counts), and short screens shrink the visual (dropping it below 600px) and tighten the spacing. "Start guided tour" starts the tour (Figma
 * "Flow / Guided tour"); `listening` is the tour's voice step, which turns the flock into its listening ring.
 */
export function Welcome({
  name,
  onAsk,
  onStartTour,
  listening = false,
}: {
  name: string;
  onAsk: (question: string) => void;
  onStartTour: () => void;
  listening?: boolean;
}) {
  return (
    <section className="@container flex w-full flex-col items-center gap-7 py-4 [@media(max-height:760px)]:gap-4 [@media(max-height:760px)]:py-0">
      {/* The design's "murmuration" visual (246 × 115). */}
      {/* Smaller on short windows, and dropped only when there's really no room. */}
      <div
        data-tour="flock"
        className="relative grid h-28.75 w-61.5 shrink-0 place-items-center [@media(max-height:760px)]:h-20 [@media(max-height:760px)]:w-43 [@media(max-height:600px)]:hidden"
      >
        <Flock className="size-full" listening={listening} />
        {listening && (
          <p role="status" className="absolute bottom-2 text-sm text-muted">
            Listening…
          </p>
        )}
      </div>
      <h2 className="text-center text-4xl font-light tracking-[-0.5px] text-navy lg:text-5xl [@media(max-height:760px)]:text-4xl">
        {greetingFor(new Date())}, <span className="text-accent-bright">{name}.</span>
      </h2>
      <p className="text-center text-xl text-ink [@media(max-height:760px)]:text-lg">
        Your plan moved this week: savings are up $120, and retirement still needs attention. Where shall we start?
      </p>
      <button
        type="button"
        onClick={onStartTour}
        className="h-12 shrink-0 rounded-full border border-primary px-6 text-base font-bold text-primary transition-colors hover:bg-info-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        Start guided tour
      </button>
      <div data-tour="cards" className="grid w-full grid-cols-1 gap-2.75 @xl:grid-cols-2 @4xl:grid-cols-4">
        {STARTERS.map(({ icon: Icon, title, body, action }, i) => (
          <article
            key={title}
            data-tour={i === STARTERS.length - 1 ? "automations" : undefined}
            className={
              "flex flex-col gap-3 rounded-lg border border-line bg-white p-5 shadow-hairline transition duration-200 ease-out " +
              // Lifts a little on hover, and when its button has keyboard focus; stays put for reduced motion.
              "hover:-translate-y-1 hover:shadow-card focus-within:-translate-y-1 focus-within:shadow-card " +
              "motion-reduce:transition-none motion-reduce:hover:translate-y-0 motion-reduce:focus-within:translate-y-0"
            }
          >
            <Icon aria-hidden className="size-10 text-accent" strokeWidth={1.75} />
            <h3 className="pt-3 text-lg font-bold text-navy">{title}</h3>
            <p className="flex-1 pt-1.5 text-sm text-muted">{body}</p>
            <div className="py-2">
              <AiButton className="w-full" aria-label={`${action.label}: ${title}`} onClick={() => onAsk(action.prompt)}>
                {action.label}
              </AiButton>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
