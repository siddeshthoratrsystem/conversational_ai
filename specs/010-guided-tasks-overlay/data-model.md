# Data model: Guided tasks overlay

Static, in-app content. Nothing is stored or sent.

## GuidedTaskSection

| Field | Type | Notes |
|---|---|---|
| `title` | string | "Budgeting", "Retirement", "Debt", "Savings" (fixed order) |
| `tasks` | GuidedTask[] | at least one |

## GuidedTask

| Field | Type | Notes |
|---|---|---|
| `title` | string | Exact copy from spec FR-004 |
| `description` | string | Exact copy from spec FR-004 |
| `icon` | GuidedTaskIconName | `bell-alert`, `wallet`, `receipt`, `bill`, `refresh`, `pie-chart`, `line-chart`, `building`, `bank`, `people` |

No state transitions: tasks have no action in this slice. UI state is a single `tasksOpen` boolean in `ChatApp`.
