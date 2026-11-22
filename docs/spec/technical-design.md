# Technical design

- **Status:** draft — gate G2 pending
- **Date:** 2026-11-22
- **Owns:** how it is built. Behavior is in
  [functional-design.md](functional-design.md); deployment is in
  [knative/README.md](../../knative/README.md) (linked, not duplicated).

## 1. Context

Python 3.12 + FastAPI service wrapping Google ADK agents driven by LiteLLM, with
Neo4j as the graph store and Redis for session state and the build queue. A React
SPA (Vite) is served by the same process. Everything is configured from
environment variables via `pydantic-settings`.

Pinned for reproducibility (see `requirements.txt`): `fastapi==0.165.0`,
`google-adk==2.15.0`, `litellm==1.82.6` (deliberately below the compromised
1.82.7/1.82.8), `neo4j==6.4.1`, `neo4j-graphrag[openai]==1.24.0`, `redis==8.1.0`,
`pydantic==2.14.4`.

## 2. Architecture

```
┌──────────────────────────── browser ─────────────────────────────┐
│ React 19 SPA (Vite, Tailwind 4, shadcn + AI Elements)            │
│  useChat ── DefaultChatTransport ──► POST /sessions/{id}/chat     │
│  TanStack Query ────────────────────► REST (/sessions, /jobs)     │
│  ArtifactCard registry ◄── data-* parts                           │
└───────────────────────────────┬──────────────────────────────────┘
                                │ same origin (one Knative Service)
┌───────────────────────────────▼──────────────────────────────────┐
│ FastAPI                                                           │
│  /                    → ui/dist (StaticFiles + SPA fallback)       │
│  /sessions…           → existing routers + list/delete/patch       │
│  /sessions/{id}/chat  → SSE, x-vercel-ai-ui-message-stream: v1     │
│  /jobs/{id}           → polled                                     │
│  AdkAgentRunner.run_stream() → ADK partial events                  │
└───────────────────────────────────────────────────────────────────┘
        │ Redis (sessions, jobs, owner index, queue)   │ Neo4j 5.26+ (self-managed)
        ▼                                              ▼
   worker Deployment (JOB_RUNNER=worker) ────────► graph build
```

**Components**

| Component | Responsibility |
|---|---|
| `app/routers/*` | HTTP surface, one router per lesson/stage |
| `app/agents/*` | ADK agents, prompts, tools (docstrings name L4–L8) |
| `app/agents/runner.py` | Stateless ADK runner: hydrate state → run → persist |
| `app/construction/*` | L8 structured/unstructured build + job runner |
| `app/graph/*` | Neo4j driver wrapper, Cypher, `is_write_query` |
| `app/state/*` | `StateStore` (memory / Redis), sessions, jobs, queue |
| `app/config.py` | The entire configuration surface |
| `ui/` | Vite SPA (M0+) |

## 3. Data model

```python
class SessionRecord(BaseModel):          # M1 adds owner_id + title
    id: str                              # 32 hex
    owner_id: str                        # sha256(subject)[:16]
    title: str | None                    # <= 80 chars
    created_at: datetime
    updated_at: datetime
    state: dict[str, Any]                # notebook keys (state_keys.py)
    history: dict[str, list[ChatTurn]]   # per-agent transcript

class SessionSummary(BaseModel):         # sidebar; never the full state
    id: str; title: str | None
    stage: Literal["goal","files","schema","build","query"]
    created_at: datetime; updated_at: datetime

class Job(BaseModel):                    # unchanged
    id: str; session_id: str; status: JobStatus
    progress: float; steps: list[str]
    payload: dict[str, Any]; result: dict[str, Any] | None; error: str | None
```

`stage` is derived, never stored: the presence of
`approved_user_goal` → `approved_files` → `approved_construction_plan` → a job →
a query determines it. One derivation function, used by the API and the UI.

Redis layout: `session:{id}` (hash/JSON), `sessions:{owner}` (ZSET scored by
`updated_at`), `jobs:{id}`, `queue:jobs` (list). Listing is O(page), never a
`SCAN` over all sessions.

## 4. Protocols

| Concern | Choice | Why |
|---|---|---|
| Chat transport | UI Message Stream v1 over SSE (`x-vercel-ai-ui-message-stream: v1`) | What AI SDK UI / AI Elements consume; supports parts and approvals |
| REST | JSON, Pydantic models | Existing contract; `/docs` stays accurate |
| Progress | `202` + poll `GET /jobs/{id}` | Works with Knative timeouts; SSE optional later |
| Queue | Redis `BRPOP` | Simple; worker Deployment; reliable-queue upgrade documented |
| Static | `StaticFiles` + SPA fallback | Same origin removes CORS and cookie complexity |

## 5. Streaming implementation

`AdkAgentRunner.run_stream()` is a sibling of `run()`:

1. Build the agent and a throwaway `InMemorySessionService` exactly as `run()` does.
2. Iterate `runner.run_async(...)`; for each event with `partial` text, yield the
   delta.
3. Suppress sub-agent text for composite agents (`SequentialAgent`,
   `LoopAgent`) — only the outer agent's final response is user-facing. This
   avoids the schema agents' internal chatter leaking into the transcript.
4. Persist `session.state` + `history` once, after the stream completes (not per
   delta).
5. On provider error, emit an `error` part; the partial text stays visible.

The endpoint owns the frame envelope (start/text-end/finish), the `data-artifact`
parts, and the 15 s `: ping`. Keep-alive is what makes a slow turn survive
Knative's response-start timeout.

## 6. Concurrency and statelessness

- Requests hold no session state in memory; each turn hydrates from `StateStore`
  and writes back (Factor VI). This is what allows scale-to-zero.
- A streaming request occupies a Knative concurrency slot for its lifetime
  (`containerConcurrency: 10`, `maxScale: 5` → at most 50 concurrent turns).
- Builds run out-of-band: `inprocess` (BackgroundTasks) for local, `worker`
  (Redis + Deployment) in the cluster. `worker` is mandatory on Knative.
- `run_stream` and `run` share the agent registry, so behavior cannot drift.

## 7. Security

| Control | Design |
|---|---|
| Auth (M1) | `AUTH_MODE=cookie\|oidc\|none`; `none` only when `ENVIRONMENT=dev`; HttpOnly, Secure, SameSite=Lax cookie |
| CSRF | `SameSite=Lax` + required `X-Requested-With: kg-ui` on mutations; no wildcard CORS with credentials |
| IDOR | `owner_id` filter on every session route; foreign ids return 404 |
| Cypher | READ routing + `is_write_query()` rejection; per-owner rate limit; hash-only logging |
| LLM cost | Per-owner quotas, `LLM_DAILY_BUDGET`, `max_tokens`, `maxScale` |
| XSS | Markdown with raw HTML disabled; CSP `default-src 'self'`; no `dangerouslySetInnerHTML` |
| Secrets | Env/Secret only; `SecretStr` in settings; `.env` git-ignored; plan-gate secret scan |
| Logs | request id + method/path/status; never prompt bodies or Cypher text |

Threat model note: the public URL plus an LLM key is a spending endpoint. Auth is
a launch blocker for the UI (decision in [ADR-0004](adr/0004-multi-session-history.md)),
not a later hardening step.

## 8. Non-functional requirements

| ID | Requirement | Target / check |
|---|---|---|
| **NFR-1** | Scale-to-zero must not lose sessions or jobs | `STATE_BACKEND=redis` + `JOB_RUNNER=worker`; verified in M4 |
| **NFR-2** | A single turn fits the request ceiling | < 300 s; longer work must use `/build` |
| **NFR-3** | Cold start is tolerable | ≤ 5 s p50 after warm-up; `minScale=1` for live demos |
| **NFR-4** | Memory fits the pod limit | ≤ 1 Gi/pod under demo load; raise if OOMKilled |
| **NFR-5** | No secrets in git | `git grep` patterns + plan gate + review checklist |
| **NFR-6** | Time to first byte on a stream | headers ≤ 2 s; first `ping` within 15 s |
| **NFR-7** | Accessibility | zero serious/critical axe violations on core states |
| **NFR-8** | Abuse resistance | per-owner rate limits, daily budget, `maxScale` |
| **NFR-9** | Read-only Cypher guarantee | write clauses → 400 always, independent of the UI |
| **NFR-10** | Observability without leakage | request id on every response; no prompt/Cypher text in logs |
| **NFR-11** | Session listing scales with page size | ZSET cursor pagination, no `SCAN` |
| **NFR-12** | Reproducible builds | exact pins + lockfile + one image per commit |

## 9. Test strategy

| Layer | Tool | Scope |
|---|---|---|
| Unit / integration (backend) | pytest | Flow, preconditions, tools, jobs, query modes, health — 26 tests today |
| Stream contract | pytest + golden `.sse` fixtures | Frame order, header, error parts, `[DONE]` (M1) |
| Gate | `unittest` | `tests/test_check_plan_sync.py` (8 tests, no deps) |
| Components | Vitest + Testing Library | `ArtifactCard` per kind, approvals, keyboard |
| E2E | Playwright | No-LLM journey, reload resume, session switch, console refusal (M3) |
| A11y | `@axe-core/playwright` | Empty, streaming, results, console (M4) |
| Real Neo4j | pytest (opt-in) | `RUN_NEO4J_IT=1` domain graph + root-cause query |

Evals (the playbook's Phase 4) are an **M1 deliverable**: the no-LLM journey and
the stream contract become the first eval cases, so agent-configuration changes
are regression-tested, not just code.

## 10. Known limitations

- **Last write wins** when two tabs edit the same session; optimistic concurrency
  (`If-Match: updated_at`) is deferred.
- **SIGKILL during a build** leaves a job `running` forever; the worker traps
  SIGTERM, but a reliable queue (Redis Streams + ack) is the real fix.
- **`memory` state backend** is dev-only and incompatible with the worker.
- **No stream resume**: a dropped connection restarts the turn; the prompt is
  replayed rather than resumed.
- **Aura cannot run the CSV build** (`file:///`); self-managed Neo4j is required
  until the loader speaks `https://`.
- **Frontend majors differ**: `ai@7` vs `@ai-sdk/react@4`; pinned together.

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| AI Elements migration (standalone → shadcn, Nov 2026) | Build breaks on upgrade | Install from the shadcn registry; components are vendored |
| ADK 2.x API drift | Runner breaks | Pinned version; `tests/test_adk_runner.py` |
| Knative 300 s ceiling | Long schema turns fail | Streaming + keep-alive; jobs for long work |
| Provider outage | 502s | Error part + retry; any LiteLLM provider |
| Doc drift | Agents act on stale facts | Same-commit rule, plan gate, docs lint (planned) |

## 12. Alternatives considered

See ADRs: [0001](adr/0001-chat-ui-stack.md) (UI stack),
[0002](adr/0002-vite-same-origin.md) (Vite/same-origin),
[0005](adr/0005-knative-topology.md) (Knative topology). Rejected options are
recorded there rather than re-argued here.
