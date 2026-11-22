# Product design

- **Status:** draft — gate G2 pending
- **Date:** 2026-11-22
- **Owns:** who this is for, what the journey feels like, and what the UI must
  communicate. Exact behavior lives in [functional-design.md](functional-design.md).

## Personas

| Persona | Context | Wants | Fears |
|---|---|---|---|
| **Course learner** ("Ada") | Following the DeepLearning.AI course, has the notebooks open | To see the L4→L8 agents actually run, and to understand what each stage decided | That she has to debug Jupyter to see the demo |
| **Evaluating engineer** ("Ben") | Evaluating whether this repo is worth reading/forking | A quick local win, honest docs, a clean API; no API key to try it | Another half-finished demo, hidden keys, a UI that lies about state |
| **Operator** ("You") | Runs the public demo on Knative | Low cost, no abuse, fast rollback | A public endpoint burning tokens unattended |

Design consequence: the **LLM-free path is a first-class product**, not a
fallback. It is how Ben succeeds in five minutes and how the repo is evaluated.

## Jobs to be done

1. *When I have product and supplier CSVs plus review text, I want to see them
   become one graph, so I can trace complaints to a supplier.*
2. *When an agent proposes a schema, I want to inspect and correct it before it
   is used, so I stay accountable for the model's choices.*
3. *When the graph is built, I want to ask a question in English and also see
   the Cypher, so I can trust and reuse the answer.*
4. *When I come back tomorrow, I want my session still there, so I don't rebuild
   a graph to ask one more question.*

## Journey

The course's five stages are the product's information architecture. Each stage
ends in a human decision, and the UI's job is to make that decision obvious.

| # | Stage | The user sees | The user does | Gate |
|---|---|---|---|---|
| 1 | **Goal** (L4) | A conversation; the agent reflects back "kind of graph" + description | Confirms in chat, or edits the goal card | Approve goal |
| 2 | **Files** (L5) | Available files in `DATA_DIR`, plus the agent's picks | Deselects what is irrelevant | Approve files |
| 3 | **Schema** (L6/L7) | Node/relationship rules table with critic feedback; entity and fact types | Edits via feedback, or accepts; can load the known-good plan | Approve schema |
| 4 | **Build** (L8) | Progress bar and an ordered step log | Waits, or cancels | Job completes |
| 5 | **Query** | Answer text, the Cypher, and a result grid | Asks a follow-up, opens the console, edits Cypher | — |

Two interaction modes share one page: **chat** for stages 1–2 and 5, **artifacts**
for stages 3–4. The sidebar is history; the stage rail is progress; the composer
is always contextual.

## Information architecture

```
┌──────────────┬──────────────────────────────────────┬────────────────┐
│ Sessions     │ Chat + artifacts                     │ Stage rail     │
│ + New        │  assistant text…                     │ ① Goal    ✓    │
│ ▸ root cause │  [GoalCard] [FilesCard]              │ ② Files   ✓    │
│   schema v2  │  [SchemaRulesCard] [BuildCard]       │ ③ Schema  ●    │
│   demo       │  [QueryCard: answer + Cypher + grid] │ ④ Build        │
│ [search]     │                                      │ ⑤ Query        │
│              │  [ composer: stage-aware hint ]      │ Session facts  │
└──────────────┴──────────────────────────────────────┴────────────────┘
```

- URL: `/` (redirects to last session) and `/s/{sessionId}` (deep-linkable).
- Sidebar is collapsible; on narrow screens it becomes an overlay and the stage
  rail collapses to a 5-dot stepper.
- Session facts (files, node count, last build) are read-only and derived from
  session state, never separately editable.

## Screen inventory

| Screen | Purpose | Key components |
|---|---|---|
| Session empty state | Explain the product and offer the demo path | suggestions, `Load demo session`, `NoApiKeyNotice` |
| Chat thread | Conversation and inline artifacts | AI Elements `Conversation`/`Message`, `ArtifactCard` |
| Session sidebar | History, rename, delete | `SessionSidebar`, `SessionRow` |
| Stage rail | Progress and gating | `StageRail` |
| Cypher console | Author and run queries | `CypherConsole`, `ParamsEditor`, `ResultGrid` |
| Settings (later) | Theme, retention, auth | — |

## UX states

Every state must be designed, not defaulted:

| State | What the user sees |
|---|---|
| **Empty** | One-sentence explainer, three suggestions, demo button |
| **Cold start** (scale-to-zero) | After 800 ms without headers: "Waking the service…" with retry |
| **Streaming** | Token stream with a stage label; Stop button; `Esc` cancels |
| **Approval pending** | The artifact card is the focus; composer hints "Approve to continue" |
| **Building** | Progress + step log; the composer stays usable for other questions |
| **Error** | Inline, actionable: what failed, Retry, request id |
| **Expired session** | Banner + one-click new session; the typed draft survives |
| **No API key** | Chat disabled with an explanation; defaults path still enabled |
| **Empty history** | Illustration + `New session` + `Load demo session` |

## Content and tone

- The composer placeholder changes with the stage ("Approve the schema to
  continue", "Ask about your graph…"). This is how gating feels intentional
  rather than broken.
- Errors never surface raw exception text or stack traces; they name the failed
  dependency ("the LLM provider rejected the key") and offer a next action.
- Artifacts use the domain's words — *node construction*, *fact type* — not
  generic "item" language. See [../vocabulary.md](../vocabulary.md).

## Accessibility

- Streaming text: the active message is `aria-live="polite"` and `aria-busy`;
  the transcript is not a live region (avoids re-announcing deltas).
- Keyboard: `Enter` send, `Shift+Enter` newline, `Esc` stop/close,
  `Mod+Enter` run query, focus moves to a new artifact, visible focus rings.
- Status is never color-only (icon + label); contrast ≥ 4.5:1;
  `prefers-reduced-motion` disables shimmer and slide.
- Target: zero serious/critical `axe` violations on empty, streaming, results,
  and console states.

## Brand

- Dark-first, neutral shadcn tokens, a single graph-green accent reserved for
  graph/query visuals; light mode supported.
- Typography: system/Inter for UI, monospace for Cypher and params.
- No marketing hero, no illustration-heavy onboarding: the product is the graph.

## Non-goals

Mobile-native apps, i18n, guided tours, graph visualization, file upload,
comparison across sessions, sharing links with other users.

## Product metrics

| Metric | Target | Why |
|---|---|---|
| Time to first graph (no key) | < 5 min from clone | INT-1/INT-2 |
| Steps requiring `curl` | 0 after M3 | INT-4 |
| Demo completion without key | 100% | Public repo evaluation |
| Session return rate (demo) | ≥ 20% within 24 h | INT-5/multi-session value |
| Serious a11y violations | 0 | NFR-7 |
