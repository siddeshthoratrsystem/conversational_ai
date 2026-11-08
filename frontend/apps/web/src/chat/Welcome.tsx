import { ChartPie, Scale, TrendingUp, Wallet, type LucideIcon } from "lucide-react";

import { AiButton } from "@convai/ui/ai-button";
import { AlfredOrb } from "@convai/ui/logo";

// One click sends these from an empty chat (spec 005).
export const SUGGESTIONS: { icon: LucideIcon; question: string; detail: string }[] = [
  { icon: Wallet, question: "What is my portfolio worth?", detail: "See your total and what each holding adds up to." },
  {
    icon: ChartPie,
    question: "How does my allocation compare to my target?",
    detail: "Check stocks, bonds and cash against your plan.",
  },
  { icon: Scale, question: "Do I need to rebalance?", detail: "Find out whether your mix has drifted too far." },
  {
    icon: TrendingUp,
    question: "Project $500 a month at 6% for 20 years",
    detail: "See what steady saving could grow to.",
  },
];

export function greetingFor(date: Date): string {
  const hour = date.getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/**
 * Empty chat (Figma S1 "AI home"): greeting and suggestion cards. Choosing a card asks Alfred that question.
 * Sized to fit above the composer: the cards go 1 → 2 → 4 across with the space this section gets (a container
 * query, so the History panel counts), and short screens drop the orb and tighten the spacing.
 */
export function Welcome({
  name,
  onAsk,
  showSuggestions = true,
}: {
  name: string;
  onAsk: (question: string) => void;
  /** Spec 009: planning shortcuts are hidden without full access. */
  showSuggestions?: boolean;
}) {
  return (
    <section className="@container flex w-full flex-col items-center gap-6 py-4 [@media(max-height:760px)]:gap-4 [@media(max-height:760px)]:py-0">
      <AlfredOrb className="size-12 [@media(max-height:760px)]:hidden" />
      <h2 className="text-center text-4xl font-light tracking-[-0.5px] text-navy lg:text-5xl [@media(max-height:760px)]:text-4xl">
        {greetingFor(new Date())}, <span className="text-accent-bright">{name}.</span>
      </h2>
      <p className="max-w-150 text-center text-xl text-ink [@media(max-height:760px)]:text-lg">
        Ask about your holdings, allocation, rebalancing or savings projections. Answers use demo data and are for
        information only.
      </p>
      {/* Figma S1 card: icon, bold title, short text, then the full-width gradient button. */}
      {showSuggestions && (
        <div className="grid w-full grid-cols-1 gap-2.75 @xl:grid-cols-2 @4xl:grid-cols-4">
          {SUGGESTIONS.map(({ icon: Icon, question, detail }) => (
            <article key={question} className="flex flex-col gap-3 rounded-lg border border-line bg-white p-5 shadow-hairline">
              <Icon aria-hidden className="size-10 text-accent" strokeWidth={1.5} />
              <h3 className="pt-1 text-lg font-bold text-navy">{question}</h3>
              <p className="flex-1 text-sm text-muted">{detail}</p>
              <AiButton className="mt-1 w-full" aria-label={`Ask Alfred: ${question}`} onClick={() => onAsk(question)}>
                Ask Alfred
              </AiButton>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
