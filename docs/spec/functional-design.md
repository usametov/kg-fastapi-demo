# Functional design

- **Status:** draft — gate G2 pending
- **Date:** 2026-11-22
- **Owns:** exact behavior — stages, contracts, errors, acceptance criteria.
  Product intent is in [product-design.md](product-design.md); implementation is
  in [technical-design.md](technical-design.md).

## 1. Stage machine

A session is a state machine whose transitions are *human approvals*. The
precondition of each stage is the key the previous stage approved; the domain
keys are copied verbatim from the notebooks
([`app/domain/state_keys.py`](../../app/domain/state_keys.py)).

| Stage | Agent(s) | Precondition | Action | Writes | Approve / set directly |
|---|---|---|---|---|---|
| **L4 Goal** | `user_intent` | none | chat turn(s) | `perceived_user_goal` | `POST /goal/approve` → `approved_user_goal`; `PUT /goal` sets both |
| **L5 Files** | `file_suggestion` | `approved_user_goal` | suggest + approve | `suggested_files` | `POST /files/approve` → `approved_files`; `PUT /files` validates against `DATA_DIR` |
| **L6 Structured** | `schema_structured` (LoopAgent) | `approved_user_goal`, `approved_files` | propose; optional `feedback` | `proposed_construction_plan`, `feedback` | `POST /schema/structured/approve`; `PUT …?use_default=true` |
| **L7 Unstructured** | `schema_unstructured_entities` → `…_facts` (or `…_all`) | `approved_user_goal` | NER then fact types | `proposed_entity_types`, `proposed_fact_types`, `approved_unstructured_files` | `POST …/approve-entities` then `…/approve`; `PUT …?use_default=true` |
| **L8 Build** | worker / background | `approved_construction_plan` (+ entity types when `include_unstructured`) | job | `Job` record | — (job completes) |
| **Query** | `graphrag` or none | built graph | named / Cypher / question | none (read-only) | — |

Guards are enforced server-side. A precondition miss returns **409** with a
machine-readable body; the UI pre-disables the action so the 409 is a backstop,
not the normal path.

```json
{ "detail": "approved_files missing", "missing_stage": "files", "action": "complete L5 first" }
```

## 2. Session lifecycle

- `POST /sessions` creates a session with an empty `state` and `history`; `201`.
- `GET /sessions/{id}` returns `SessionView` (`id`, timestamps, `state`).
- Sessions expire after `STATE_TTL_SECONDS` (default 86 400).
- With `STATE_BACKEND=memory` a process restart loses sessions; the UI must
  treat `404` as "expired", not as a fatal error.
- With `STATE_BACKEND=redis` any replica serves any session (required on Knative).
- Ownership (M1): every session has `owner_id`; reads and writes filter on it,
  and a foreign session returns **404**, never 403.

## 3. API surface

### Existing (implemented)

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/health` | — | `{status, version, env}` (no dependency calls) |
| GET | `/health/ready` | — | `{neo4j, state_store, state_backend, llm_configured}`; 503 when a dependency is down |
| POST | `/sessions` | — | `201 SessionView` |
| GET | `/sessions/{id}` | — | `SessionView` |
| POST | `/sessions/{id}/goal` | `{message}` | `ChatResponse` |
| POST | `/sessions/{id}/goal/approve` | — | `UserGoal` |
| PUT | `/sessions/{id}/goal` | `UserGoal` | `UserGoal` |
| GET | `/sessions/{id}/files/available` | — | `{files: string[]}` |
| POST | `/sessions/{id}/files` | `{message?}` | `ChatResponse` |
| POST | `/sessions/{id}/files/approve` | — | `FilesBody` |
| PUT | `/sessions/{id}/files` | `{files}` | `FilesBody` (422 on unknown files) |
| POST | `/sessions/{id}/schema/structured` | `{feedback}` | `StructuredSchemaResponse` |
| POST | `/sessions/{id}/schema/structured/approve` | — | `StructuredSchemaResponse` |
| PUT | `/sessions/{id}/schema/structured?use_default=` | plan or nothing | `StructuredSchemaResponse` |
| POST | `/sessions/{id}/schema/unstructured` | `{phase, feedback}` + `?review_files=` | `UnstructuredSchemaResponse` |
| POST | `/sessions/{id}/schema/unstructured/approve-entities` | — | `UnstructuredSchemaResponse` |
| POST | `/sessions/{id}/schema/unstructured/approve` | — | `UnstructuredSchemaResponse` |
| PUT | `/sessions/{id}/schema/unstructured?use_default=` | schema or nothing | `UnstructuredSchemaResponse` |
| POST | `/sessions/{id}/build` | `{include_structured, include_unstructured, reset_graph}` | `202 JobView` |
| GET | `/jobs/{id}` | — | `JobView` |
| POST | `/query` | exactly one of `cypher`, `named`, `question` (+`params`, `limit`) | `QueryResponse` |

### Planned (M1–M3)

| Method | Path | Purpose | M |
|---|---|---|---|
| POST | `/sessions/{id}/chat` | SSE chat turn (UI Message Stream v1) | M1 |
| GET | `/sessions` | paginated session summaries for the sidebar | M1 |
| GET | `/sessions/{id}/messages` | transcript as `KgUIMessage[]` | M1 |
| PATCH | `/sessions/{id}` | rename (`{title}`) | M1 |
| DELETE | `/sessions/{id}` | delete | M1 |
| POST | `/auth/login`, `/auth/logout`, `GET /auth/me` | cookie session | M1 |

## 4. Streaming contract

`POST /sessions/{id}/chat` returns `text/event-stream` with
`x-vercel-ai-ui-message-stream: v1`.

Request: the AI SDK standard body plus `agent`:

```json
{ "id": "chat-1", "messages": [/* UIMessage[] */], "agent": "auto" }
```

Frame order for a successful turn:

```text
data: {"type":"start","messageId":"msg_01"}
data: {"type":"start-step"}
data: {"type":"text-start","id":"t1"}
data: {"type":"text-delta","id":"t1","delta":"Got it — a "}
data: {"type":"text-end","id":"t1"}
data: {"type":"data-artifact","id":"artifact-goal","data":{…}}
data: {"type":"finish-step"}
data: {"type":"finish"}
data: [DONE]
```

Rules:

- `: ping` every 15 s while no data is flowing (Knative response-start timeout).
- A failure after headers is an `error` part, not a truncated body:
  `data: {"type":"error","errorText":"…"}`.
- Pre-stream failures are plain JSON `4xx` (the client has not committed to a
  stream yet).
- `text-delta` is only emitted for the outer, user-facing agent. Sub-agent
  chatter from `SequentialAgent`/`LoopAgent` is buffered into the final text.
- Multiple artifacts are allowed in one turn; each has a stable `id`.

## 5. Artifacts

One discriminated union drives one renderer:

```ts
type KgArtifact =
  | { kind: "goal"; goal: UserGoal; approved: boolean }
  | { kind: "files"; available: string[]; suggested: string[]; approved: string[] | null }
  | { kind: "structured_schema"; rules: Record<string, Construction>; criticFeedback?: string; approved: boolean }
  | { kind: "unstructured_schema"; entities: string[]; facts: FactType[]; approvedEntities: boolean; approved: boolean }
  | { kind: "build"; jobId: string; status: JobStatus; progress: number; steps: string[]; result?: unknown; error?: string }
  | { kind: "query"; mode: "cypher" | "named" | "question"; cypher?: string; records: Record<string, unknown>[]; answer?: string; ms?: number };
```

- **Reconcile by id.** A `data-artifact` part with an existing `id` updates that
  card; a new id appends.
- **Approval patch.** Approvals are REST calls; on success the client replaces
  the artifact with the server's canonical object (same id), so the card shows
  `Approved ✓` without a second stream.
- Artifacts are never the source of truth: `GET /sessions/{id}` is.

## 6. Errors

| Condition | Status | Shape | UI |
|---|---|---|---|
| Stage gate | 409 | `{detail, missing_stage, action}` | Inline hint + jump to stage |
| Unknown session | 404 | `{detail}` | Expired-session banner |
| Foreign session | 404 | `{detail}` | Same as unknown (no oracle) |
| Unknown file in `PUT /files` | 422 | `{detail}` | Inline list of bad names |
| Write clause in `/query` | 400 | `{detail}` | "This console is read-only" banner |
| LLM/provider failure | 502 | `{detail}` | Retry + request id |
| Failure mid-stream | 200 | `error` part | Retry the turn |
| Unauthenticated (M1) | 401 | `{detail}` | Redirect to login |
| Rate limit (M1) | 429 | `{detail, retry_after}` | Countdown + explanation |

## 7. Cypher console

Exposed to end users by decision [ADR-0003](adr/0003-expose-raw-cypher.md).

- Editor: CodeMirror 6 with Cypher language support
  (`@neo4j-cypher/react-codemirror`, stable line 1.0.4); completion seeded from
  `CALL db.schema.visualization()` (already wrapped in `app/graph/cypher.py`).
- Params: JSON object editor with inline validation; sent as `params`.
- Named queries insert a **template** into the editor; they never auto-run.
- Limit control 1–1000 (default 25) applies to templates; raw Cypher is not
  rewritten server-side.
- Write clauses are rejected by `is_write_query()` → 400; the refusal renders
  inline and preserves the editor content.
- Results: column inference, arrays as chips, nulls as `—`, footer with row
  count and elapsed ms, copy as CSV/JSON, virtualized beyond 100 rows.
- History: last 20 runs per session in `localStorage`, re-runnable, clearable.
- Logging: query **hash** and row count only — never query text or params.

## 8. Multi-session history

- Sidebar lists `SessionSummary` (id, title, stage, timestamps), grouped by
  recency, paginated 50 per page with an opaque cursor.
- Title derives from the approved `kind_of_graph`, else the first user message
  truncated to 60 chars; user rename wins; max 80 chars.
- Switching sessions aborts the in-flight stream and loads messages + state.
- Delete asks for confirmation, removes optimistically, restores on failure.
- Two tabs on one session: last write wins (documented limitation, see
  [technical-design.md](technical-design.md#10-known-limitations)).

## 9. Functional requirements

Format: **FR-n** — statement. *Acceptance:* observable check. Test IDs are
reserved and tracked in [traceability.md](traceability.md).

| ID | Requirement | Acceptance | M |
|---|---|---|---|
| **FR-1** | A session advances only through goal → files → schema → build → query | Calling a later stage early returns 409 with `missing_stage`; the UI disables the action | M1 |
| **FR-2** | Goal chat is multi-turn and approval copies perceived → approved | Two turns keep history; approve returns the same goal under `approved_user_goal` | exists |
| **FR-3** | File suggestion is approvable or directly settable, validated against `DATA_DIR` | Unknown file returns 422; valid list is copied to `approved_files` | exists |
| **FR-4** | Structured schema returns typed node/relationship rules, approvable or defaulted | `use_default=true` yields the known-good plan and marks it approved | exists |
| **FR-5** | Unstructured schema proposes entities and fact types with two-stage approval | `phase=facts` before entity approval returns 409 | exists |
| **FR-6** | Build runs as a background job with progress, even with no LLM key | `include_unstructured=false` builds the CSV graph; job reaches `succeeded` | exists |
| **FR-7** | Query supports named, raw read-only Cypher, and natural language | Write clause → 400; named query returns records; question returns answer + cypher | exists |
| **FR-8** | Chat streams tokens and artifacts over the UI Message Stream protocol | Frame order and header match §4; mid-turn failure produces an `error` part | M1 |
| **FR-9** | Artifacts render inline and approvals update them in place | Approving patches the existing card by id; no duplicate card | M2 |
| **FR-10** | A raw Cypher console with params, limit, history, and read-only refusal | A valid query renders a grid; a `CREATE` is refused inline with content preserved | M3 |
| **FR-11** | Session history: list, open, rename, delete, isolated per owner | Foreign id → 404; rename persists; delete removes it from the list | M1 |
| **FR-12** | A reload restores the transcript and stage | `GET …/messages` reproduces the thread; the rail reflects state | M1 |
| **FR-13** | Authentication protects every session and query route | Unauthenticated → 401; mutation without `X-Requested-With` → 403 | M1 |
| **FR-14** | The SPA is served same-origin by FastAPI without shadowing the API | `/s/{id}` returns `index.html`; `/sessions`, `/docs`, `/health` still work | M2 |
| **FR-15** | The no-LLM demo path works end-to-end from the UI | Defaults + structured-only build + `graph_summary` with no provider key | M2 |

Out-of-scope behaviors (uploads, sharing, graph viz) are listed in
[product-design.md](product-design.md#non-goals) and are not requirements.
