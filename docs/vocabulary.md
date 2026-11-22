# Vocabulary

One term per concept, and the synonyms to avoid. Agents invent vocabulary when a
project does not fix it; this file exists to stop that.

## Process terms

| Term | Meaning | Avoid |
|---|---|---|
| **Intent** | `intent.md` — why the project exists, its success criteria and non-goals | "requirements doc", "PRD" |
| **Spec** | The Design-phase gate: `docs/spec/spec.md` plus the three design docs | "design doc" (ambiguous) |
| **Plan** | `plan.md` — the current milestone, ordered work, files that change | "roadmap", "backlog" |
| **Gate** | A human decision point (G1 intent, G2 spec, G3 plan, G4 review, G5 release) | "approval step", "sign-off" |
| **Artifact** | Any committed evidence (intent, spec, plan, ADR, diff, review) | "document" (too vague) |
| **ADR** | Architecture Decision Record; immutable, superseded rather than edited | "decision log entry" |
| **FR / NFR** | Functional / non-functional requirement with a permanent ID | "feature", "ticket" |
| **Manifest** | The bullet list of paths/globs under `## Files that change` | "file list" |
| **Eval** | A task + checks that regress-test agent behavior, not just code | "test" (it is a test *of the agent*) |

## Course and lesson terms

| Term | Meaning | Avoid |
|---|---|---|
| **L2–L8** | The course lessons; every module docstring names its lesson | "step 4", "stage" |
| **API mode** | One-shot agent execution behind HTTP, with explicit `/approve` endpoints, instead of the notebooks' interactive chat | "headless mode" |
| **Perceived goal** | What the agent thinks the user wants (`perceived_user_goal`) | "proposed goal" |
| **Approved goal** | The human-confirmed goal (`approved_user_goal`) that later stages read | "final goal" |
| **Node construction** | A rule that turns a CSV column set into nodes of one label | "node spec", "entity rule" |
| **Relationship construction** | A rule that MERGEs relationships between two labels from one CSV | "edge rule" |
| **Construction plan** | The collection of node + relationship rules for the CSVs | "schema" (reserve that for L7 and graph schema) |
| **Fact type** | A `(subject, predicate, object)` type triple for review text, e.g. `(Product, has_issue, Issue)` | "relation type" |
| **Domain graph** | The graph built from CSVs via L8 structured import | "structured graph" |
| **Lexical graph** | The graph extracted from review markdown by `SimpleKGPipeline` | "unstructured graph", "text graph" |
| **Entity resolution** | Linking extracted `__Entity__` nodes to domain nodes with `CORRESPONDS_TO` | "deduplication", "matching" |
| **`__Entity__`** | The label `SimpleKGPipeline` puts on extracted nodes | "entity node" |
| **`CORRESPONDS_TO`** | The relationship created by entity resolution | "SAME_AS", "matches" |
| **GraphRAG** | The L8 agent that turns a question into Cypher and an answer | "RAG" |
| **Named query** | A vetted query in `NAMED_QUERIES` (`graph_summary`, `root_cause`, `products_with_issues`) | "preset", "canned query" |
| **Root-cause query** | The course's motivating query: products with issues → their parts' suppliers | "the big query" |

## System terms

| Term | Meaning | Avoid |
|---|---|---|
| **Session** | `SessionRecord`: state + per-agent history, addressed by id | "conversation", "thread" (the UI thread is a view of a session) |
| **Stage** | One of goal / files / schema / build / query, derived from session state | "phase" |
| **Artifact card** | A UI card rendering one `KgArtifact` | "widget", "panel" |
| **Reconcile by id** | An incoming `data-artifact` part with an existing id updates that card | "merge", "replace" |
| **Approval patch** | Replacing a card with the server's canonical object after `/approve` | "refresh" |
| **Job** | A background build (`Job`), polled via `GET /jobs/{id}` | "task" (reserve for plan tasks) |
| **Worker** | `python -m app.worker`, a Redis queue consumer (a Deployment, not a Knative Service) | "background service" |
| **State backend** | `memory` (dev) or `redis` (any replica, survives scale-to-zero) | "cache" |
| **Job runner** | `inprocess` (BackgroundTasks) or `worker` (Redis queue) | "queue mode" |
| **UI Message Stream** | The SSE protocol with `x-vercel-ai-ui-message-stream: v1` | "SSE format", "AI stream" |
| **Data part** | A typed `data-*` frame carrying an artifact | "payload", "metadata" |
| **Same-origin** | The SPA and API served by one FastAPI process | "monolith" |
| **Scale-to-zero** | Knative scaling a Service to 0 replicas when idle | "autoscale down" |

## Banned ambiguity

- **"Schema"** alone: say *construction plan* (CSV rules) or *unstructured schema*
  (entity + fact types) or *graph schema* (labels currently in Neo4j).
- **"Graph"** alone: say *domain graph* or *lexical graph*.
- **"Approved"** alone: say which key (`approved_user_goal`, `approved_files`, …).
- **"Session"** vs **"chat thread"**: a session is the server record; a chat
  thread is its UI rendering.
