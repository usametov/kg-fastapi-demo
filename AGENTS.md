# AGENTS.md — repository memory

Read this before changing anything. Keep it under one page; if it grows, move
detail into `docs/` and link it.

## Commands

| Task | Command | Healthy output |
|---|---|---|
| Plan gate (what CI runs) | `python scripts/check_plan_sync.py --base origin/main --head HEAD` | no output, exit 0 |
| Plan gate tests | `python3 -m unittest tests.test_check_plan_sync -v` | `Ran 8 tests … OK` |
| Backend tests | `python -m pytest -q` (needs `pip install -r requirements-dev.txt`) | all passed |
| Real-Neo4j test | `RUN_NEO4J_IT=1 NEO4J_PASSWORD=… python -m pytest -q tests/test_integration_neo4j.py` | passed or skipped |
| Run the API | `python -m app` | uvicorn on `:8000`, JSON logs |
| Local stack | `docker compose up --build` | `/health/ready` → 200 |
| Load sample data | `python -m scripts.load_sample_data --with-reviews` | nodes/relationships counts |
| Reset graph | `python -m scripts.reset_graph --yes` | constraints dropped |

Python 3.12 in the image; 3.13/3.14 also run the gate tests. No Node yet —
`ui/` is a spec until M0.

## Layout

| Path | What |
|---|---|
| `app/` | FastAPI: routers, agents, construction, graph, state, config |
| `ui/` | Vite SPA (M0+); `ui/SPEC.md` is a retired pointer |
| `docs/spec/` | spec index, product/functional/technical design, ADRs, traceability |
| `docs/playbook.md` | the SDLC loop, gates, why the plan gate is a script |
| `docs/vocabulary.md` | canonical terms — use them, do not invent synonyms |
| `knative/` | deployment guide + manifests (operational) |
| `intent.md` | why the project exists; the top of the document chain |
| `plan.md` | current milestone + the file manifest the gate checks |
| `evals/` | empty until M1 (see `plan.md`) |

## Conventions

- All I/O crosses a Pydantic model (`app/domain/models.py`); no bare dicts in
  handlers.
- Configuration only via `Settings` (`app/config.py`); never read `os.environ`
  in feature code.
- Secrets are `SecretStr`; never log a `Settings` object or its fields.
- Dependencies and services are injected with `Depends` / `Annotated`; tests
  override them — do not add module-level globals.
- Module docstrings name the course lesson they came from (L2–L8); keep that
  convention when adding modules.
- Prompts and Cypher are adapted from the course and `neo4j-contrib/agentic-kg`
  (MIT). Credit the source in the docstring, not in a comment thread.
- Frontend (M0+): TypeScript strict, no `any`, components from
  `components/ai-elements/` are vendored and may be edited.

## Guardrails

- **Never commit** `.env`, keys, tokens, or real data. Only `.env.example` and
  `knative/secret.example.yaml` with placeholders.
- **Never edit a test to make it pass.** If the test is wrong, say why and change
  it in a separate, explicit commit with the reasoning.
- **Never add an unpinned dependency** (Python: exact `==`; Node: exact version +
  lockfile).
- **Never change `data/` or `knative/` manifests without a plan entry.**
- **Never touch `app/agents/prompts.py`** without noting which lesson it came
  from and why the deviation is needed.
- **Never log** prompt bodies, Cypher text, or session state.

## Plan gate (required for implementation changes)

1. Read `plan.md`. If your change is not covered, stop.
2. If it belongs, add the path under `## Files that change` **in the same
   commit** — the gate accepts entries added by the change it checks.
3. Keep `- Status: Approved` only while the maintainer has approved that plan.
4. Run the gate locally before pushing.

Process artifacts (docs, `intent.md`, `plan.md`, `AGENTS.md`, `REVIEW.md`,
`.github/`, `evals/`) never need a plan entry.

## Documentation duty

Every behavior change updates, in the **same commit**:

| If you changed… | Update |
|---|---|
| An endpoint, frame, error code, or stage rule | `docs/spec/functional-design.md` + the FR row in `docs/spec/traceability.md` |
| Architecture, model, dependency, security posture | `docs/spec/technical-design.md` (+ ADR if it is a decision) |
| User-visible journey, state, or copy | `docs/spec/product-design.md` |
| A decision | New `docs/spec/adr/NNNN-*.md`; never edit an accepted one |
| The work itself | `plan.md` manifest + status |

## Definition of done

- [ ] Behavior matches the spec; any deviation is an ADR.
- [ ] Tests added/updated; command output pasted as evidence.
- [ ] Docs and traceability updated.
- [ ] Plan manifest covers all changed implementation paths.
- [ ] `python scripts/check_plan_sync.py` exits 0.
- [ ] No secrets, no unpinned deps, no test edits to force a pass.

## Known traps

| Trap | Reality |
|---|---|
| `ai@7` and `@ai-sdk/react@4` | Independent major versions — pin both, commit the lockfile |
| `LOAD CSV … "file:///"` | Reads **Neo4j's** import dir; Aura does not support it |
| `PORT` on Knative | Knative injects it from `containerPort`; do not set it in the ConfigMap |
| `STATE_BACKEND=memory` + worker | The worker exits: memory state is per-process |
| `ENVIRONMENT` | `Literal["dev","test","prod"]` — no `staging` |
| `litellm` | Must stay `<1.82.7` (1.82.7/1.82.8 were compromised on PyPI) |
| UI Message Stream | Responses need `x-vercel-ai-ui-message-stream: v1` or `useChat` ignores them |
| Session keys | `proposed_entity_types` / `approved_entity_types`, not `*_entities` |
| Approvals | REST, idempotent, no LLM call — do not route them through the stream |

## When in doubt

- The decision is architectural → ADR, then code.
- The decision is behavioral → functional design, then code.
- The decision is about scope → `intent.md`, and stop until the maintainer
  answers.
