import { GuidedTaskIcon, type GuidedTaskIconName } from "@convai/ui/guided-task-icon";

type GuidedTask = { title: string; description: string; icon: GuidedTaskIconName };

// Figma "Evo / Guided tasks overlay", copy as designed (spec 010 FR-004). The Debt and Savings icons are not in the
// design yet; they are provisional picks from the same icon set (spec 010 research R2).
export const GUIDED_TASK_SECTIONS: { title: string; tasks: GuidedTask[] }[] = [
  {
    title: "Budgeting",
    tasks: [
      {
        title: "Get a heads-up before you overspend",
        description: "A standing alert tied to your category targets.",
        icon: "bell-alert",
      },
      {
        title: "Catch a cash shortfall before it happens",
        description: "Forecasting your balance against what's coming.",
        icon: "wallet",
      },
      {
        title: "Get a monthly spending report, automatically",
        description: "A recurring readout, no need to ask.",
        icon: "receipt",
      },
      {
        title: "Find out if you're overpaying on your bills",
        description: "A standing check against current offers.",
        icon: "bill",
      },
    ],
  },
  {
    title: "Retirement",
    tasks: [
      {
        title: "Automatically raise your 401(k) contribution every year",
        description: "Set a rule, like raising it 1% every January or whenever you get a raise, up to a cap you choose.",
        icon: "refresh",
      },
      {
        title: "Make sure your investments still match your risk tolerance",
        description: "A standing check across your retirement and taxable accounts.",
        icon: "pie-chart",
      },
      {
        title: "Run what-if scenarios on your retirement plan",
        description: "Ask things like “what if I retire at 62 and move somewhere cheaper.",
        icon: "line-chart",
      },
    ],
  },
  {
    title: "Debt",
    tasks: [
      {
        title: "Put your debt payoff on autopilot",
        description: "Pick avalanche, snowball, or a custom strategy.",
        icon: "refresh",
      },
      {
        title: "Get notified when refinancing could save you money",
        description: "A standing watch on rates and offers against your profile.",
        icon: "bank",
      },
      {
        title: "Compare debt payoff strategies side by side",
        description: "See total interest, your debt-free date, and what extra payments change.",
        icon: "line-chart",
      },
    ],
  },
  {
    title: "Savings",
    tasks: [
      {
        title: "Roll an old 401(k) into one place",
        description: "Tell me where your old plan is and I’ll handle the paperwork and the call to your former provider.",
        icon: "building",
      },
    ],
  },
];

/** The design's "more-horizontal" glyph. Shown but inert for now, so it is not a button (spec 010 FR-007). */
function MoreMarker() {
  return (
    <span aria-hidden data-more className="shrink-0 pt-1 text-ink">
      <svg viewBox="0 0 20 20" className="size-5" fill="currentColor">
        <circle cx="4.17" cy="10" r="1.67" />
        <circle cx="10" cy="10" r="1.67" />
        <circle cx="15.83" cy="10" r="1.67" />
      </svg>
    </span>
  );
}

/**
 * Guided tasks overlay (Figma "Evo / Guided tasks overlay", desktop). Covers the chat area while the chat stays
 * mounted underneath. Tasks don't start anything yet, so rows are plain list items.
 */
export function GuidedTasks() {
  return (
    <section
      id="guided-tasks"
      aria-labelledby="guided-tasks-title"
      className="absolute inset-0 z-20 overflow-y-auto bg-white pt-16"
    >
      <div className="mx-auto w-full max-w-189.5">
        <div className="flex flex-col gap-1.5 px-10 pt-9 pb-4">
          <h2 id="guided-tasks-title" className="text-display-sm font-light tracking-[-0.5px] text-navy">
            Guided tasks
          </h2>
          <p className="text-base text-muted">
            Guided tasks I can take you through, start to finish. Pick one and I’ll do the heavy lifting.
          </p>
        </div>
        <div className="flex flex-col gap-7 px-10 pb-10">
          {GUIDED_TASK_SECTIONS.map((section) => (
            <div key={section.title} className="flex flex-col gap-6 pt-2">
              <h3 className="text-xl font-bold text-navy">{section.title}</h3>
              <ul className="flex flex-col gap-6">
                {section.tasks.map((task) => (
                  <li key={task.title} className="flex items-start gap-5">
                    <GuidedTaskIcon name={task.icon} />
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <p className="text-lg font-bold text-navy">{task.title}</p>
                      <p className="text-base text-muted">{task.description}</p>
                    </div>
                    <MoreMarker />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
