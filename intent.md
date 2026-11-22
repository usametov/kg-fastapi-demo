# Intent

- **Status:** proposed — gate G1 pending owner sign-off
- **Owner:** Alan Samet
- **Date:** 2026-11-22
- **Supersedes:** none

> The content is agreed; only the gate signature is pending. Flip the status to
> `accepted` to let work proceed under this intent (see [playbook](docs/playbook.md)).

## Problem

The DeepLearning.AI course *Agentic Knowledge Graph Construction* (Kollegger /
Neo4j) ships as notebooks: a multi-agent system that agrees on a goal, proposes
files and schemas, builds a knowledge graph from CSVs and review text, and
answers a root-cause question across the two graphs. Notebooks demonstrate but
do not operate. Nothing can be called by another system, nothing survives a
kernel restart, and there is no way for someone who is not running Jupyter to
see the workflow happen.

## Proposed outcome

A stateless service that exposes the course workflow over HTTP, plus a browser UI
that makes the approval gates visible and operable. Someone can clone the repo,
run one command, and watch a knowledge graph get built from sample data — with
or without a language-model API key — then ask the course's root-cause question
and inspect the Cypher behind the answer.

## Users

| User | What they need |
|---|---|
| **Course learner** | See the L4→L8 agents work without re-running notebooks |
| **Evaluating engineer** | A readable API, honest docs, and a local path that needs no key |
| **Graph practitioner** | A real Cypher console against a real graph |
| **Maintainer** (you) | A public artifact that stays correct as dependencies move |

## Success criteria

| # | Criterion | How it is observed |
|---|---|---|
| **INT-1** | A fresh clone reaches a ready service in under 5 minutes | `docker compose up` → `/health/ready` green (Neo4j + Redis + API + worker) |
| **INT-2** | The full graph build works with **no LLM key** | `PUT …/schema/structured?use_default=true`, build `include_unstructured=false`, `graph_summary` returns rows |
| **INT-3** | The course's motivating question is answerable | `POST /query {"named":"root_cause"}` returns products, issues, suppliers |
| **INT-4** | The workflow is drivable from the browser | M1–M3: no `curl` required for goal → files → schema → build → query |
| **INT-5** | The public deployment is safe to expose | Auth on every session route, read-only Cypher, rate limits, no secrets in git |
| **INT-6** | Docs are usable by humans *and* agents | `intent.md`, `spec.md` + 3 designs, ADRs, `AGENTS.md`, plan gate |

## Constraints

- Public MIT repository; adapted code credited to `neo4j-contrib/agentic-kg`.
- Python 3.12, FastAPI, Google ADK, LiteLLM, Neo4j 5.26+, neo4j-graphrag.
- Neo4j 5.26+ is a floor, not a preference: dynamic labels and `CALL (row) {}`.
- The CSV build uses `LOAD CSV … "file:///…"`, so Neo4j must be self-managed
  (Aura does not support `file:///`) — see `knative/README.md`.
- Knative: scale-to-zero, 300 s request ceiling, concurrency-based autoscaling.
- Single maintainer; agents do most of the editing.

## Out of scope

- Multi-tenant SaaS, billing, orgs, RBAC beyond per-owner isolation.
- OpenAI `/v1/chat/completions` wire compatibility (it cannot express a human gate).
- Graph visualization (Neo4j Browser already exists), file uploads, i18n,
  mobile-native apps, mobile responsive *beyond* a usable narrow layout.

## Assumptions

- The course defines the vocabulary (L4–L8); see [vocabulary](docs/vocabulary.md).
- Sample data is fictional and safe to publish.
- LiteLLM can front any provider; OpenAI is one option, not a requirement.
- A single operator can satisfy the human gates (G1, G3, G5).

## Risks

| Risk | Mitigation |
|---|---|
| LLM spend if the public URL is abused | Auth + per-owner quotas + `maxScale` + daily budget (M1) |
| Course/dependency drift breaks parity | Pinned deps; docstrings name the lesson; `tests/test_flow.py` |
| Neo4j Aura cannot run the CSV build | Self-managed Neo4j documented as required; Aura only after an `https://` loader |
| Frontend version skew (`ai@7` vs `@ai-sdk/react@4`) | Exact pins + lockfile; verified in M0 |
| Docs drift from code | Same-commit rule + plan gate + docs lint (planned) |

## Open questions

Tracked in [docs/spec/spec.md](docs/spec/spec.md#open-questions). Questions that
are decided move to an ADR; this file keeps only what is still unresolved.
