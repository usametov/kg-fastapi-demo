# UI Chat Interface — Design Spec

- **Status:** approved for build (decisions locked 2026-11-22)
- **Owner:** Alan Samet
- **Scope:** the React chat UI for the `kg-fastapi-demo` FastAPI service, its wire contract,
  the backend changes it requires, and its Knative deployment
- **Implementation status:** not started. This document is the contract; `ui/` contains no code yet.

---

## 1. Locked decisions

| # | Decision | Rationale | Date |
|---|---|---|---|
| D1 | **Vite + React 19 SPA** in `ui/`, served by FastAPI at `/` | Simplest thing that works; no SSR need; same-origin in prod removes CORS entirely | 2026-11-22 |
| D2 | **Deploy on Knative** as one Service (API + static UI), worker as a `Deployment` | Scale-to-zero for the demo, same-origin cookies, no CORS, one image | 2026-11-22 |
| D3 | **Raw Cypher editor exposed to end users** | It is the point of the demo; the server already rejects writes and runs with READ routing | 2026-11-22 |
| D4 | **Multi-session history** with a session sidebar | Users need to return to a graph build; requires server-side listing + ownership | 2026-11-22 |
| D5 | Chat spine = **AI SDK UI v7** (`useChat`) + **AI Elements** from the shadcn registry | Best composition and typing; `data-*` parts and tool-approval parts map onto our stage workflow | 2026-11-22 |

D3 + D4 + a public Knative URL mean **authentication is a launch blocker, not a polish item** (§16, M1).

## 2. Scope and non-goals

**In scope:** goal chat (L4), file selection (L5), structured/unstructured schema approval (L6/L7),
build progress (L8), GraphRAG Q&A, raw Cypher console, multi-session history, auth, Knative manifests.

**Out of scope:** OpenAI `chat/completions` compatibility layer, multi-tenant orgs/RBAC beyond
per-owner isolation, file uploads, streaming graph visualization (Neo4j Browser already exists),
i18n, mobile-native apps.

## 3. What "OpenAI-compatible" means — and which layer we target

| Layer | Meaning | Decision |
|---|---|---|
| **A. Model provider** | Backend can call OpenAI or any OpenAI-compatible base URL | ✅ Already supported: `LLM_MODEL`, `LLM_API_BASE`, `OPENAI_API_KEY` via LiteLLM |
| **B. Wire protocol** | `/v1/chat/completions`-shaped HTTP (messages, deltas, `tool_calls`) | ❌ Not built. It cannot express a human approval gate |
| **C. UI kit** | React chat components | ✅ Target of this spec |

The React components do not consume layer B; they consume the **AI SDK UI Message Stream**
(layer C's native protocol). Layer B can be added later as a facade without touching the UI.

## 4. Gap analysis: today's API vs. what the UI needs

| Need | Today | Work |
|---|---|---|
| Token streaming | `AdkAgentRunner.run()` returns only the last full text (`app/agents/runner.py:124-131`) | Add `run_stream()` yielding ADK partial-event deltas |
| One conversational URL | 5 stage-specific REST endpoints | Add `POST /sessions/{id}/chat` (SSE) |
| CORS | none (`app/main.py`) | Dev-only (Vite proxy is primary); `UI_ORIGINS` for split deploys |
| Transcript after reload | `SessionView` has `state` only, not `history` | Add `GET /sessions/{id}/messages` |
| Session list | none | `GET /sessions`, `DELETE`, `PATCH`; `StateStore.list_sessions()` |
| Ownership | sessions are anonymous | `owner_id` on `SessionRecord`, filter every read |
| Auth | none | Cookie session or OIDC; `AUTH_MODE` |
| Stage gating | prose `409` bodies | Structured `detail` + `missing_stage`; client pre-disables |
| Build progress | poll `GET /jobs/{id}` | Reuse polling in M3; SSE optional |
| Cypher console | `POST /query` accepts `cypher` + `params` | UI only; no backend change |

## 5. Stack and exact versions

Verified against the npm registry on **2026-11-22**. Pin these; commit the lockfile.

| Package | Version | Note |
|---|---|---|
| `react`, `react-dom` | `19.3.1` | AI Elements requires React 19 |
| `vite` | `8.3.8` | |
| `tailwindcss` | `4.3.5` | v4 CSS-first config |
| `ai` | `7.0.179` | Core types + transports |
| `@ai-sdk/react` | `4.0.183` | **Independent major from `ai`** — do not assume they match |
| `@tanstack/react-query` | `5.108.2` | Session list, job polling, cache |
| `@neo4j-cypher/react-codemirror` | `1.0.4` | Stable line. The `latest` tag currently points at `2.0.0-next.*`; pin `1.0.4` explicitly and re-evaluate after 2.0 ships |
| shadcn/ui components | current registry | AI Elements + base components |
| `sonner`, `next-themes`, `lucide-react` | current | Toasts, dark mode, icons |

> ⚠️ **Do not scaffold from `elements.ai-sdk.dev`.** That project is deprecated at the end of
> November 2026. Install from the shadcn registry instead:
>
> ```bash
> npx shadcn@latest add @ai-elements/message @ai-elements/conversation \
>   @ai-elements/prompt-input @ai-elements/response @ai-elements/reasoning \
>   @ai-elements/tool @ai-elements/confirmation @ai-elements/loader
> ```
>
> Files are vendored into `src/components/ai-elements/` and are ours to edit.

## 6. Architecture

```
┌──────────────────────────── browser ─────────────────────────────┐
│ React 19 SPA (Vite)                                              │
│  useChat ── DefaultChatTransport ──► POST /sessions/{id}/chat    │
│  TanStack Query ────────────────────► REST (/sessions, /jobs)   │
│  ArtifactCard registry ◄── data-* parts                          │
│  SessionSidebar ◄── GET /sessions                                │
└───────────────────────────────┬──────────────────────────────────┘
                                │ same origin in prod (one Knative Service)
┌───────────────────────────────▼──────────────────────────────────┐
│ FastAPI                                                           │
│  /                    → ui/dist (StaticFiles + SPA fallback)      │
│  /sessions…           → existing routers + list/delete/patch      │
│  /sessions/{id}/chat  → SSE, x-vercel-ai-ui-message-stream: v1    │
│  /jobs/{id}           → existing (polled)                         │
│  AdkAgentRunner.run_stream() → ADK partial events                 │
└───────────────────────────────────────────────────────────────────┘
             │ Redis (sessions, jobs, owner index)   │ Neo4j 5.26+ (self-managed)
             ▼                                       ▼
        worker Deployment (JOB_RUNNER=worker) ── consumes Redis queue
```

**Dev:** `vite` on `:5173`, proxy `/sessions`, `/jobs`, `/query`, `/health`, `/auth` → `localhost:8000`.
No CORS needed locally either, but the middleware is added for preview deployments.

**Prod:** the SPA is built in a Docker stage and copied to `/app/ui/dist`; `UI_DIST_DIR` points at it.
One image, one origin, `SameSite=Lax` cookies work without CORS.

**Static serving rule:** mount assets at `/assets` (hashed, immutable cache) and serve `index.html`
only for non-API `GET` paths. Never let the SPA fallback swallow `/sessions`, `/jobs`, `/query`,
`/health`, `/docs`, `/openapi.json`, `/auth`.

## 7. Wire contract

### 7.1 Chat endpoint

```
POST /sessions/{session_id}/chat
Content-Type: application/json
Accept: text/event-stream

{ "id": "<chat id>", "messages": [UIMessage…], "agent": "auto|user_intent|file_suggestion|graphrag" }
```

- Body is the **AI SDK standard** shape (`messages`, `id`, `trigger`, `messageId`) plus our optional
  `agent`, so `DefaultChatTransport({ api, body: { agent } })` works unmodified.
- The backend uses the **last user text part** as the prompt. Prior turns live in server-side
  `history`, so the client transcript is display state, not context.
- Pre-stream failures are **plain JSON 4xx** (`404` session, `409` stage gate, `422` bad body).
  Mid-stream failures are an `error` part on an open `200` stream.

### 7.2 Frames

```text
data: {"type":"start","messageId":"msg_01"}
data: {"type":"start-step"}
data: {"type":"text-start","id":"t1"}
data: {"type":"text-delta","id":"t1","delta":"Got it — a "}
data: {"type":"text-delta","id":"t1","delta":"supply-chain graph."}
data: {"type":"text-end","id":"t1"}
data: {"type":"data-artifact","id":"artifact-goal","data":{"kind":"goal","goal":{…},"approved":false}}
data: {"type":"finish-step"}
data: {"type":"finish"}
data: [DONE]
```

Required headers: `Content-Type: text/event-stream`, `x-vercel-ai-ui-message-stream: v1`,
`Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`.
Send `: ping\n\n` every 15 s while idle (satisfies Knative's response-start timeout and proxy idling).

### 7.3 Custom data parts

One discriminated union; one renderer. `id` is stable per stage so stream updates and local approval
patches reconcile in place instead of stacking duplicate cards.

```ts
// ui/src/lib/stream-types.ts — mirrored by pydantic models server-side
type ArtifactKind =
  | "goal" | "files" | "structured_schema"
  | "unstructured_schema" | "build" | "query";

type KgArtifact =
  | { kind: "goal"; goal: UserGoal; approved: boolean }
  | { kind: "files"; available: string[]; suggested: string[]; approved: string[] | null }
  | { kind: "structured_schema"; rules: Record<string, Construction>; criticFeedback?: string; approved: boolean }
  | { kind: "unstructured_schema"; entities: string[]; facts: FactType[]; approvedEntities: boolean; approved: boolean }
  | { kind: "build"; jobId: string; status: JobStatus; progress: number; steps: string[]; result?: unknown; error?: string }
  | { kind: "query"; mode: "cypher" | "named" | "question"; cypher?: string;
      records: Record<string, unknown>[]; answer?: string; ms?: number };

export type KgUIMessage = UIMessage<never, {
  artifact: KgArtifact;                                              // part.type === "data-artifact"
  notice: { level: "info" | "success" | "error"; text: string };     // "data-notice", transient
}>;
```

`notice` parts are written with `transient: true` so they never enter stored history.

### 7.4 Approvals do not cross the stream

The UI calls the existing `POST …/approve` (no LLM, idempotent), receives the canonical object, and
patches the rendered artifact by reusing its `id` via `setMessages`. Benefits: approvals work while a
stream is idle, are retryable, and keep the SSE endpoint small.

## 8. Backend changes

| # | Change | Size | Notes |
|---|---|---|---|
| 1 | `POST /sessions/{id}/chat` SSE | M | Stage→agent routing; last-user-text extraction; artifact emission; keep-alives |
| 2 | `AdkAgentRunner.run_stream()` | M | Yield text from partial events; only stream from the outer user-facing agent (not sub-agents of `SequentialAgent`/`LoopAgent`); leave `run()` intact so REST + tests are unaffected |
| 3 | `GET /sessions/{id}/messages` | S | Map `history` + state → `KgUIMessage[]` for reload |
| 4 | **Session collection**: `GET /sessions`, `DELETE /sessions/{id}`, `PATCH /sessions/{id}` (title) | M | Requires `StateStore.list_sessions/delete_session` + `title`, `owner_id` on `SessionRecord` |
| 5 | **Auth** (`AUTH_MODE=none\|cookie\|oidc`) + per-owner quotas | M | §16. `none` only when `ENVIRONMENT=dev` |
| 6 | **Static serving** of `ui/dist` + SPA fallback | S | §6 rules |
| 7 | Structured `409` bodies | XS | `{detail, missing_stage, action}` so the composer can hint instead of erroring |
| 8 | Move `GET /health/ready` semantics | XS | Keep `/health` dependency-free for liveness; readiness checks Neo4j + Redis (already true) |

No existing endpoint changes shape, so the pytest suite and the README curl walkthrough stay valid.

## 9. Multi-session history

### 9.1 UX

- **Left sidebar** (collapsible, 280 px; overlay on mobile) with `New session` at the top.
- Sessions grouped **Today / Yesterday / Previous 7 days / Older**, sorted by `updated_at` desc.
- Row: auto-title, stage badge (`Schema`, `Build`, `Query`), relative time. Hover reveals
  `Rename` and `Delete`.
- **Title** = the approved `kind_of_graph` once the goal is approved; until then the first user
  message truncated to 60 chars; user renames override both. Max 80 chars, single line, no HTML.
- **Search** filters client-side across titles of loaded pages (server search is deferred; see §9.4).
- **Active session** is in the URL: `/s/{sessionId}`. Deep links are shareable to the same owner only.
- **Switching sessions**: abort any in-flight stream, cancel in-flight queries, load messages + state,
  restore that session's unsent composer draft (kept in `sessionStorage` per id).
- **Delete**: confirm dialog (`Delete “<title>”? This cannot be undone.`), optimistic removal,
  rollback + toast on failure. Deleting the active session navigates to `/` and creates a fresh one.
- **Empty history**: illustration + `New session` + `Load demo session` (no-LLM defaults path).
- **Expired session** (`404`, memory backend restarted): non-blocking banner, offer **Start new
  session**, keep the typed draft. Never a dead screen.

### 9.2 Data model additions

```python
class SessionRecord(BaseModel):
    id: str
    owner_id: str            # sha256(subject)[:16] — never an email or raw user id
    title: str | None        # ≤ 80 chars, set on goal approval or by user rename
    created_at: datetime
    updated_at: datetime
    state: dict[str, Any]
    history: dict[str, list[ChatTurn]]

class SessionSummary(BaseModel):   # what the sidebar needs; never the full state
    id: str
    title: str | None
    stage: Literal["goal", "files", "schema", "build", "query"]
    created_at: datetime
    updated_at: datetime
```

`stage` is derived from which approved keys exist in `state` (`approved_user_goal` →
`approved_files` → `approved_construction_plan` → build job → query).

```python
class StateStore(ABC):
    @abstractmethod
    async def list_sessions(self, owner_id: str, cursor: str | None, limit: int) -> tuple[list[SessionSummary], str | None]: ...
    @abstractmethod
    async def delete_session(self, session_id: str) -> None: ...
```

- **Redis**: `sessions:{owner}` ZSET scored by `updated_at`, plus `session:{id}` hash. Cursor is
  `updated_at|id` (opaque base64 to the client). `SADD`-style scan is banned — it is O(n) per page.
- **Memory**: dict + sort; fine for dev and tests.
- **Retention**: honor the existing `SESSION_TTL_SECONDS` (default 86400). Sidebar shows
  `Expires in 12 h` only when TTL < 24 h; expired ids return `404` and clean themselves up.

### 9.3 Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/sessions` | `?cursor=&limit=50` | `{ items: SessionSummary[], next_cursor }` |
| GET | `/sessions/{id}` | — | existing `SessionView` |
| GET | `/sessions/{id}/messages` | — | `KgUIMessage[]` |
| PATCH | `/sessions/{id}` | `{ title }` | `SessionSummary` |
| DELETE | `/sessions/{id}` | — | `204` |

All five filter by `owner_id`. A session owned by someone else returns **404, not 403** (no
enumeration oracle). Session ids stay 32-hex random; ownership is the control, not unguessability.

### 9.4 Deferred

Server-side title search, sharing/collaboration, archive/restore, per-session token usage accounting.
Two tabs open on one session is **last-write-wins** on `state`; optimistic concurrency
(`If-Match: updated_at`) is deferred and documented as a known limitation.

## 10. Raw Cypher console

Exposed per D3, reachable two ways: the **Cypher tab** of a query artifact, and a
`Show in console` expand control that opens a full-height editor sheet.

### 10.1 Editor

- `@neo4j-cypher/react-codemirror@1.0.4` (CodeMirror 6) for Cypher syntax highlighting,
  autocomplete, and lint diagnostics. If it conflicts with React 19 peers, fall back to
  `@uiw/react-codemirror` + `@neo4j-cypher/codemirror` and record the decision here.
- Server-driven completion: labels/relationship types can be seeded from
  `CALL db.schema.visualization()` (already wrapped as `PHYSICAL_SCHEMA` in `app/graph/cypher.py`)
  into the completion source; refresh on session switch and after a build.
- **Params**: side-by-side JSON editor (monospace, 300 px min height) with inline validation
  (`params must be a JSON object`). `params` is sent as-is; the server already passes it to the driver.
- **Named query picker**: `graph_summary`, `root_cause`, `products_with_issues` from
  `app/graph/cypher.py:NAMED_QUERIES` insert a **template into the editor**; they never auto-run, so
  the user sees the Cypher before it executes.
- **Limit** control 1–1000, default 25, injected into templates only (raw Cypher is not rewritten).
- **Run**: `Mod+Enter`. Button shows a spinner and is disabled until the previous run settles.
  `Esc` closes the console sheet.

### 10.2 Result rendering

- Column inference from `records[0]` keys; nested arrays (e.g. `collect(DISTINCT issues)`) render as
  chips with a `+N` overflow popover; nulls render as a muted `—`.
- Footer: row count, elapsed `ms`, mode badge, `Copy CSV`, `Copy JSON`.
- Errors (`400` from `is_write_query`, Cypher syntax, missing label) render inline under the editor in
  a non-destructive banner that keeps the editor content. Write queries show a specific hint:
  "Write clauses are rejected on this endpoint — this console is read-only."
- Results are virtualized beyond 100 rows; column widths persist per session in `localStorage`.

### 10.3 Safety

- The server's `is_write_query()` gate is the only real control; the UI never claims otherwise.
- No auto-run on paste or on template insert; no query persisted in URLs.
- Query history: **last 20 per session in `localStorage`**, re-runnable, clearable. Text only.
- **Logging**: log a SHA-256 prefix of the query plus row count, never the query text (parameters can
  contain PII).
- Per-owner rate limit applies to `/query` the same as `/chat`.
- Empty state explains the graph model with 2 example queries for the sample data (root-cause path).

## 11. Screens and information architecture

One page, three regions. Chat is the spine; artifacts are inline; stage state and session list are
always visible.

```
┌──────────────┬──────────────────────────────────────┬────────────────┐
│ Sessions     │ Chat column                          │ Stage rail     │
│ + New        │  assistant text…                     │ ① Goal    ✓    │
│ ▸ root cause │  ┌ ArtifactCard (goal) ────────────┐ │ ② Files   ✓    │
│   schema v2  │  │ [Approve] [Edit] [Reject]       │ │ ③ Schema  ●    │
│   demo       │  ├ ArtifactCard (structured) ──────┤ │ ④ Build        │
│ [search]     │  │ rules table · critic feedback   │ │ ⑤ Query        │
│              │  │ [Approve] [Use default]         │ │                │
│              │  └─────────────────────────────────┘ │ Session facts  │
│              │  [ composer… ]                       │ files 5 · 0 nodes│
└──────────────┴──────────────────────────────────────┴────────────────┘
```

- **Composer is stage-aware**: placeholder, enabled state, and hint derive from `useStage()`
  ("Approve the schema to continue") so users never hit a surprise `409`.
- **Artifact cards** carry their own primary actions; actions stay disabled after approval and show
  `Approved ✓` with a timestamp.
- **Query answers** render as `AnswerText` + `QueryArtifact` (Cypher disclosure collapsed by default,
  "Show Cypher" expands, "Open in console" for editing).
- **Build card**: progress bar, ordered step log (live), `structured only` toggle, and a note when
  `include_unstructured` needs an OpenAI key.
- **No-LLM demo**: `Load demo session` uses `PUT /schema/structured?use_default=true` and
  `PUT /schema/unstructured?use_default=true`, then builds with `include_unstructured=false`.
  Chat input is disabled with an explanation when no provider key is configured.

## 12. Component inventory

| Region | Component | Source |
|---|---|---|
| Thread | `Conversation`, `ConversationContent`, `ConversationScrollButton` | AI Elements |
| Messages | `Message`, `MessageContent`, `MessageResponse`, `MessageActions` | AI Elements |
| Composer | `PromptInput`, `PromptInputTextarea`, `PromptInputSubmit`, `PromptInputTools` | AI Elements |
| Reasoning/tool chatter | `Reasoning`, `Tool`, `Task` (collapsed) | AI Elements |
| Streaming | `Loader`, `Shimmer` | AI Elements |
| Approvals | `Confirmation` (Approve/Deny/Edit variants) | AI Elements, restyled |
| Cypher | `CodeBlock` | AI Elements |
| Schema | `SchemaDisplay` + shadcn `Tabs`/`Table` | AI Elements + shadcn |
| Records | shadcn `DataTable` (sort, copy CSV) | shadcn |
| Chart | shadcn `Chart` (parts per supplier, bar) | shadcn |
| Toasts | `sonner` | shadcn |
| **Custom** | `SessionSidebar`, `SessionRow`, `StageRail`, `ArtifactCard`, `GoalCard`, `FilesCard`, `SchemaRulesCard`, `EntityFactCard`, `BuildCard`, `QueryCard`, `CypherConsole`, `ParamsEditor`, `ResultGrid`, `ConnectionStatus`, `ErrorBanner`, `NoApiKeyNotice`, `ThemeToggle` | `src/components/kg/` |

`ArtifactCard` is the only component that switches on `KgArtifact["kind"]`; everything else stays
generic and reusable.

## 13. Client state model

- **Session id** in `/s/{id}`; `lastSessionId` mirrored in `localStorage` for `/` redirect.
- **Transcript**: `useChat<KgUIMessage>({ id: sessionId, transport })`. Client messages are display
  truth; server `history` is model context.
- **Server state**: TanStack Query keys `["sessions"]`, `["session", id]`, `["messages", id]`,
  `["job", jobId]`. Invalidate `["session"]` + `["messages"]` after approvals; invalidate
  `["sessions"]` after `updated_at` changes (approve/build/rename).
- **Resume**: `GET /sessions/{id}/messages` → `setMessages`. If `404`, show the expired-session banner.
- **Build**: patch the `BuildCard`; poll `GET /jobs/{id}` at 2 s with backoff to 10 s; stop on
  `succeeded|failed`; the `jobId` is persisted in the artifact so reload resumes polling.
- **Abort**: switching sessions, `Esc`, or unmount calls `stop()` and aborts the fetch.

## 14. Edge cases

| Case | Behavior |
|---|---|
| Stage gate (`409`) | Inline hint + jump-to-step button, no raw error text |
| LLM failure (`502`) | `error` part → `ErrorBanner` with **Retry**, settings hint, request id |
| Stream drops | Keep partial text, mark message errored, offer Retry of the same prompt |
| Cold start after scale-to-zero | After 800 ms without response headers show "Waking the service…" skeleton; retry once |
| Long schema turn (>60 s) | `: ping` keep-alive keeps the connection; skeleton with stage label |
| `include_unstructured` without a key | Preflight card explains and offers structured-only |
| Huge result set | Virtualized grid, `limit` control, server cap 1000 |
| Deleted/expired session | Banner + new session, draft preserved |
| Two tabs | Last-write-wins; a toast warns when `updated_at` moved underneath |

## 15. A11y, theme, performance

- Transcript is not a live region; the streaming bubble is `aria-live="polite"` + `aria-busy`.
- Keyboard: `Enter` send, `Shift+Enter` newline, `Esc` stop/close, `Mod+Enter` run query,
  focus moves to a newly arrived artifact, visible focus rings, skip link to composer.
- Contrast ≥ 4.5:1; status never color-only; `prefers-reduced-motion` disables shimmer/slide.
- Dark mode first via `next-themes` + shadcn tokens; Neo4j accent reserved for graph/query visuals.
- Memoize messages by id, batch deltas ~50 ms, virtualize > 200 messages, lazy-load `ResultGrid` and
  `Chart`, keep the Cypher editor out of the initial bundle (`React.lazy` on the console route).

## 16. Security and cost controls

1. **Authentication (launch blocker).**
   `AUTH_MODE=cookie` (recommended): same-origin, `HttpOnly; Secure; SameSite=Lax` cookie from
   `POST /auth/login` (single demo password or OIDC code flow). `AUTH_MODE=oidc` for the cluster's
   IdP. `AUTH_MODE=none` only when `ENVIRONMENT=dev`. `owner_id = sha256(subject)[:16]`.
2. **CSRF.** Cookie auth + `SameSite=Lax` + a required `X-Requested-With: kg-ui` header on mutations
   (cross-origin requests cannot set it without a CORS preflight we deny). No `allow_origins="*"`
   with credentials, ever.
3. **IDOR.** Every session read/write filters `owner_id`; foreign ids return `404`.
4. **Cypher console.** Exposed (D3) but requires auth, is rate-limited per owner, runs READ routing,
   rejects write clauses, and logs hashes only. Add a per-query time bound where the driver supports
   it; otherwise rely on `limit` + Neo4j read transaction timeout.
5. **Rate limits and budget.** Per owner: 30 chat turns/hour, 60 queries/hour; global daily token
   budget with a hard stop (`LLM_DAILY_BUDGET`), plus `max_tokens` caps per agent. `maxScale` on
   Knative caps concurrency.
6. **XSS.** Markdown rendered with raw HTML disabled; no `dangerouslySetInnerHTML`; CSP
   `default-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'`.
7. **Secrets.** Provider keys exist only in FastAPI env/Secret. `ui/` has no `.env`; `ui/.env*` is
   git-ignored.
8. **Logging.** Access logs keep method/path/status/rid; never prompt bodies or Cypher text.

## 17. Knative deployment

### 17.1 Topology

| Workload | Kind | Why |
|---|---|---|
| `kg-fastapi-demo` | Knative **Service** (API + static SPA) | Same origin, scale-to-zero, one image |
| `kg-fastapi-worker` | Kubernetes **Deployment** (always ≥1) | Knative Services need HTTP; a queue consumer must not scale to zero mid-build |
| `redis` | Deployment/StatefulSet or managed | Sessions, jobs, owner index, queue |
| `neo4j` | **Self-managed** StatefulSet, 5.26+, APOC | The CSV build uses `LOAD CSV … "file:///…"`, which reads Neo4j's own import dir; **Aura does not support `file:///`**. Aura is only viable after switching the loader to `https://` URLs. See `knative/README.md` §6.1 and Appendix A |

### 17.2 Service spec (key fields)

The **committed** manifests in [`knative/service.yaml`](../knative/service.yaml) already match today's
code. This is the target shape after M1/M6 land — `AUTH_MODE` and `UI_DIST_DIR` appear only when those
features exist:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: kg-fastapi-demo
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"     # "1" for a live demo
        autoscaling.knative.dev/max-scale: "5"     # bounds LLM spend
        autoscaling.knative.dev/target: "10"       # concurrency per pod
    spec:
      timeoutSeconds: 300          # SSE turns must finish inside this
      containerConcurrency: 10     # each open SSE holds a slot
      containers:
        - image: ghcr.io/usametov/kg-fastapi-demo:latest
          ports: [{ containerPort: 8000 }]
          envFrom:
            - configMapRef: { name: kg-fastapi-demo-config }
            - secretRef: { name: kg-fastapi-demo-secrets }
          env:
            - { name: AUTH_MODE, value: cookie }        # M1 (not yet in config.py)
            - { name: UI_DIST_DIR, value: /app/ui/dist } # M6 (static SPA)
          startupProbe:   { httpGet: { path: /health, port: 8000 }, failureThreshold: 30, periodSeconds: 2 }
          readinessProbe: { httpGet: { path: /health/ready, port: 8000 }, periodSeconds: 5 }
          livenessProbe:  { httpGet: { path: /health, port: 8000 }, periodSeconds: 20 }
```

### 17.3 Knative-specific constraints (read before deploying)

- **`timeoutSeconds` is the hard ceiling for a request**, including an SSE response — default 300 s,
  cluster max `max-revision-timeout-seconds` (default 600 s). Keep any single agent turn under 300 s.
  Longer work must go through the job path (`POST /build` → poll), which is already how builds work.
- **Autoscaling is concurrency-based**, and a streaming response occupies a concurrency slot for its
  whole life. Plan `containerConcurrency` (10) and `maxScale` (5) as your real LLM concurrency budget.
- **Scale-to-zero kills `inprocess` jobs.** `STATE_BACKEND=redis` + `JOB_RUNNER=worker` are mandatory;
  the README already states this. The worker must be a Deployment, not a Knative Service.
- **Probes:** liveness must stay dependency-free (`/health`); a Neo4j blip must not restart pods.
  Readiness uses `/health/ready`, so a pod leaves rotation while Neo4j/Redis are down.
- **Streaming through the queue-proxy works**, but disable response compression for
  `text/event-stream`, set `X-Accel-Buffering: no`, and keep the 15 s `: ping` so the first byte
  arrives well inside `responseStartTimeoutSeconds` (default 300 s).
- **Cold start:** Python + ADK + LiteLLM import costs ~2–5 s. `minScale: 0` is fine for the public
  demo only because the UI shows a "waking" state and the first token arrives after warm-up;
  set `minScale: 1` for demos you are presenting live.
- **Static assets:** hashed `/assets/*` with `Cache-Control: public, max-age=31536000, immutable`;
  `index.html` with `no-store` so a new deploy is picked up immediately.
- **Secrets** are created with `kubectl create secret generic kg-fastapi-demo-secrets …`;
  only `knative/secret.example.yaml` (placeholders) is committed.

### 17.4 Manifests (already in the repo)

```text
knative/
├── README.md             # full deployment guide (build, config, verify, troubleshooting)
├── kustomization.yaml    # namespace kg-demo; excludes secret.example.yaml
├── configmap.yaml        # every non-secret env var from app/config.py
├── service.yaml          # Knative Service: API (+ UI once built), port 8000, probes
├── worker.yaml           # Deployment (1 replica) for python -m app.worker
└── secret.example.yaml   # OPENAI_API_KEY / NEO4J_PASSWORD placeholders - never applied
```

`knative/README.md` documents: prerequisites, multi-arch build/push, the full env-var table,
secret creation, `kubectl apply -k knative/`, the LLM-free smoke test, dependency requirements
(including the `file:///` LOAD CSV constraint on Neo4j), scale-to-zero behavior, and troubleshooting.
The UI work only adds `UI_DIST_DIR=/app/ui/dist` to the ConfigMap and the static mount in `app/main.py`.

### 17.5 Image and CI

- **Multi-stage Dockerfile:** `node:22-alpine` runs `pnpm install --frozen-lockfile && pnpm build`;
  the Python image copies `ui/dist` → `/app/ui/dist`. One immutable image tag per commit.
- **CI:** `pytest` + stream contract tests, `pnpm -C ui ci && pnpm -C ui build`, `pnpm -C ui test`,
  Playwright e2e against the no-LLM fixture server, then image build. Existing repo CI is extended,
  not replaced.

## 18. Testing

| Layer | Tool | Asserts |
|---|---|---|
| Stream contract | pytest + httpx | header `x-vercel-ai-ui-message-stream: v1`; frame order `start → text-* → data-artifact → finish → [DONE]`; golden fixtures in `tests/fixtures/*.sse` |
| Error paths | pytest | 409/404 JSON before the stream; 502 → `error` part; abort mid-stream closes cleanly |
| Sessions | pytest | list pagination, owner filtering (404 for foreign ids), rename limits, delete idempotency |
| Auth | pytest | cookie set/verify, `X-Requested-With` enforced on mutations, expired cookie → 401 |
| Part reducer | Vitest | artifact upsert by id, transient notices dropped, approval patches replace in place |
| Cards | Vitest + Testing Library | snapshot per `ArtifactKind`; disabled/approved states; keyboard approve |
| Cypher console | Vitest | params JSON validation, write-query 400 rendering, history capped at 20 |
| E2E | Playwright | full happy path **without an LLM** (`use_default` + `include_unstructured=false`), reload resume, session switch, delete, stream abort |
| A11y | `@axe-core/playwright` | no serious violations on empty, streaming, results, and console states |

The no-LLM e2e path is the highest-value test: CI and any contributor can exercise the whole UI with
no API key, using the existing `app/domain/defaults.py` plan.

## 19. Milestones

| M | Deliverable | Est. | Exit criteria |
|---|---|---|---|
| **M0** | Scaffold `ui/` (Vite, Tailwind 4, shadcn, AI Elements), fake SSE route, pinned deps | 0.5 d | Components render; version pins confirmed; `pnpm build` green |
| **M1** | Auth, session collection (`GET/DELETE/PATCH` + owner index), `/chat` stream, `run_stream()`, sidebar, stage rail, resume | 3 d | Two owners cannot see each other's sessions; goal turn streams; reload restores |
| **M2** | Artifact cards (files + both schemas), approvals, defaults path | 3 d | Entire workflow driven from the UI with no curl |
| **M3** | Build card (poll/resume), query card, **Cypher console** (editor, params, results, history) | 3 d | Root-cause answer renders as a table; a raw query runs and a write query is refused inline |
| **M4** | Knative manifests + deploy docs, a11y pass, dark/light, Playwright e2e, screenshots | 2 d | Public URL serves UI + API; e2e green in CI; scale-to-zero verified |

≈ **11.5 engineer-days**. M0–M1 is the point of no return; everything after is additive.

## 20. Repository layout

```text
kg-fastapi-demo/
├── app/                          # FastAPI (existing) + chat.py, auth.py, static.py
├── tests/fixtures/*.sse          # golden stream transcripts (shared by pytest + Vitest)
├── knative/                      # deployment guide + manifests (see §17)
├── ui/
│   ├── SPEC.md                   # this document
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts            # dev proxy → :8000
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx               # router: / and /s/:sessionId
│       ├── lib/{api,stream-types,session,cn}.ts
│       ├── hooks/{useKgChat,useStage,useSessions,useCypherConsole}.ts
│       ├── components/ai-elements/*   # vendored from the registry
│       └── components/kg/*            # ours
└── Dockerfile                    # multi-stage: ui build → python image
```

## 21. Open questions

1. **OIDC provider** — does the cluster have Dex/Keycloak/Google available, or do we ship the simple
   demo-password cookie flow first?
2. **Retention** — keep `SESSION_TTL_SECONDS=86400` for the public demo, or extend to 7 days so
   history feels real?
3. **Neo4j** — self-managed StatefulSet is required for the current `file:///` CSV build; is switching
   the loader to `https://` URLs (enabling Aura) in scope for the demo, or deferred?
4. **`minScale`** — 0 (cheapest, cold starts) or 1 for the demo window?
5. **Brand** — Neo4j-ish palette, or neutral shadcn default with a graph-green accent?
6. **Build progress transport** — polling in M3 (planned), or spend the extra day on SSE
   `data-job` updates?

## 22. Decisions log

| Date | Change | Reason |
|---|---|---|
| 2026-11-22 | Chose AI SDK UI + shadcn AI Elements over ChatKit, assistant-ui, AG-UI | Fit with stage-gated workflow + custom artifacts; ChatKit is one web component tied to OpenAI's agent path |
| 2026-11-22 | Vite SPA served same-origin by FastAPI | Removes CORS and a second deployable; Knative-friendly |
| 2026-11-22 | Raw Cypher exposed to end users | Demo value; server already enforces read-only |
| 2026-11-22 | Multi-session history with ownership | Required by the sidebar; drives the `SessionRecord`/`StateStore` changes |
| 2026-11-22 | Auth moved to M1 | Public Knative URL + raw Cypher + per-owner sessions make it a launch blocker |
