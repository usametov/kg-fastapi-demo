# Spec (index)

- **Status:** draft — gate G2 pending
- **Date:** 2026-11-22
- **Intent:** [../../intent.md](../../intent.md)
- **Plan (current work):** [../../plan.md](../../plan.md)

This is the gate artifact for the Design phase. It is deliberately thin: it
says what the design owns, who reads which part, and what is still open. The
substance lives in three documents with different readers and review cadences.

## Read by audience

| If you are… | Read | For |
|---|---|---|
| An agent starting work | [../../AGENTS.md](../../AGENTS.md) → [../../plan.md](../../plan.md) | Commands, conventions, the current task |
| A product reviewer | [product-design.md](product-design.md) | Who it is for, the journey, UX states, scope |
| An implementer | [functional-design.md](functional-design.md) | Exact behavior, contracts, acceptance criteria |
| An implementer or SRE | [technical-design.md](technical-design.md) | Architecture, data model, security, NFRs |
| Checking coverage | [traceability.md](traceability.md) | FR → acceptance → test → milestone → status |
| Asking "why is it like this?" | [adr/](adr/) | One decision per record, immutable |
| A newcomer to the domain | [../vocabulary.md](../vocabulary.md) | L4–L8 and graph vocabulary, with banned synonyms |

Operational detail is **not** here: deployment lives in
[knative/README.md](../../knative/README.md), and this spec links to it rather
than duplicating it.

## What each document owns

| Document | Owns | Does not own |
|---|---|---|
| `product-design.md` | Personas, jobs, journey, IA, screens, UX states, a11y, brand, product metrics | Endpoint shapes, frame formats |
| `functional-design.md` | Stage machine, API surface, streaming contract, artifacts, errors, FR acceptance criteria | Implementation choices, deployment |
| `technical-design.md` | Architecture, data model, protocols, concurrency, security, NFRs, test strategy, risks | Product rationale, marketing |
| `traceability.md` | The mapping table and status | Prose |
| `adr/*.md` | Decisions and their consequences | Rationale essays (keep to 1 page) |

## The gate

`plan.md` must be **Approved** before implementation, and its `## Files that
change` manifest must cover the diff. That is enforced mechanically by
[`scripts/check_plan_sync.py`](../../scripts/check_plan_sync.py) in CI; the
rationale is in [../playbook.md](../playbook.md#3-why-the-plan-gate-is-a-script).

An implementation change that departs from the manifest must add the path to
`plan.md` **in the same change set** — the gate accepts entries added by the
change it is checking, so honesty is cheap and silent drift is not.

## Change protocol

1. A **new decision** gets a new ADR; existing ADRs are never edited.
2. A **behavior change** updates `functional-design.md` and the affected FR in
   `traceability.md` in the same commit as the code.
3. A **scope change** updates `intent.md` first (human gate G1), then this spec.
4. A **renumbering** is forbidden: IDs are permanent, so links and agent
   references survive.
5. Open questions are removed only when they become a decision (ADR) or an
   explicit non-goal.

## Open questions

| # | Question | Blocks | Owner |
|---|---|---|---|
| Q1 | OIDC provider available, or ship the demo-password cookie flow first? | M1 auth | maintainer |
| Q2 | Session retention: keep `86400` s or extend to 7 days for history? | M1 sessions | maintainer |
| Q3 | Switch the CSV loader to `https://` so Neo4j Aura becomes usable? | deployment | maintainer |
| Q4 | `minScale`: 0 (cheap) or 1 (no cold start) for the demo window? | M4 | maintainer |
| Q5 | Brand: Neo4j-ish palette or neutral shadcn with a graph-green accent? | M2 | maintainer |
| Q6 | Build progress: polling (planned) or SSE `data-job` updates? | M3 | maintainer |

Q1 and Q2 block M1 and are the two to answer first.
