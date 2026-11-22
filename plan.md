# Plan

- Status: Draft
- Gate: G3 (plan approval) — flip `Status` to `Approved` once the maintainer
  approves this milestone
- **Milestone:** M0 — UI scaffold and the streaming skeleton
- **Spec:** [docs/spec/spec.md](docs/spec/spec.md)
- **Intent:** [intent.md](intent.md)

> The plan gate (`scripts/check_plan_sync.py`) reads the `## Files that change`
> section as a bullet list of exact paths/globs, and requires the exact bullet
> `- Status: Approved` (bold is tolerated). While this plan is `Draft`, any
> implementation change fails the gate — that is the gate working, not a bug.

## Objective

Prove the whole UI path end-to-end with the least code: a Vite + React 19 + shadcn
app that renders an AI Elements chat, talking to a **fake** SSE endpoint in
FastAPI that emits the UI Message Stream protocol. No auth, no sessions, no
artifacts. If this works, protocol risk for M1 is gone.

## Files that change

- `ui/**`
- `app/routers/chat.py`
- `app/main.py`
- `tests/test_chat_stream.py`
- `.gitignore`

## Order of work

1. `ui/` scaffold: `package.json` (exact pins), `vite.config.ts` (proxy to
   `:8000`), `tsconfig.json`, Tailwind 4, shadcn init.
2. Install AI Elements from the shadcn registry:
   `message`, `conversation`, `prompt-input`, `response`, `loader`.
3. `app/routers/chat.py`: `POST /sessions/{id}/chat` emitting
   `start → text-start → text-delta… → text-end → finish → [DONE]`, with the
   required header and a 15 s `: ping`. Chunked from a canned string.
4. Wire the router in `app/main.py`.
5. `useChat` with `DefaultChatTransport`; streaming text renders; `status` drives
   the Send button.
6. Contract test in `tests/test_chat_stream.py`: header, frame order, `[DONE]`.
7. Confirm `ai@7.0.179` + `@ai-sdk/react@4.0.183` coexist; commit the lockfile.

## Risks

| Risk | Check | Fallback |
|---|---|---|
| `ai@7` / `@ai-sdk/react@4` incompatibility | Install and run `pnpm build` before writing UI logic | Pin the pair the AI SDK docs recommend; record in an ADR |
| AI Elements registry layout changed post-migration | Inspect generated files | Copy the component source from the registry and vendor it |
| SSE buffered by the dev proxy | Observe deltas arriving incrementally, not in one chunk | Set `X-Accel-Buffering: no`; check Vite proxy config |
| React 19 peer conflicts | `pnpm install` warnings | `pnpm.overrides` with a recorded reason |

## Proof

- `pnpm -C ui build` exits 0.
- `python3 -m pytest tests/test_chat_stream.py -q` passes (frame order + header).
- Manual: open the dev server, send a message, watch tokens arrive incrementally.
- Gate: `python scripts/check_plan_sync.py --base origin/main --head HEAD` exits 0
  once the plan is Approved.

## Done when

- [ ] The four commands above pass and their output is pasted in the PR.
- [ ] `docs/spec/technical-design.md` records the confirmed version pair.
- [ ] `docs/spec/traceability.md` FR-8 moves from `planned` to `partial`.
- [ ] No artifact cards, auth, or session store work has started (that is M1).

## Roadmap (not current milestone)

| M | Scope | Est. | Exit |
|---|---|---|---|
| **M0** | Scaffold + fake SSE | 0.5 d | Protocol proven |
| **M1** | Auth, session collection, real `/chat` stream, sidebar, resume, **evals** | 3 d | Two owners isolated; stream real; evals installed |
| **M2** | Artifact cards (files, both schemas), approvals, defaults path | 3 d | Full workflow without curl |
| **M3** | Build card, query card, Cypher console | 3 d | Root cause + raw query, write refused |
| **M4** | Knative deploy, a11y, e2e, docs | 2 d | Public URL, scale-to-zero verified |

## Completed

| Milestone | What landed | Date |
|---|---|---|
| Docs baseline | `intent.md`, spec + 3 designs, ADRs, vocabulary, playbook, `AGENTS.md`, `REVIEW.md`, plan gate + CI | 2026-11-22 |
| Knative | `knative/` manifests + deployment guide | 2026-11-22 |
