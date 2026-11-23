# Playbook — how we run the SDLC here

- **Status:** accepted
- **Date:** 2026-11-22
- **Source:** adapted from the AI-native SDLC playbook
  (https://github.com/bashebr/ai-native-sdlc) to a single-maintainer repository.

The upstream playbook has six phases and one rule that matters more than the
others: **every phase ends by committing an artifact, and the next phase begins by
reading it.** The commit chain is the audit trail. This page maps that loop onto
this repository — what exists, who approves, and what happens when they disagree.

## 1. The loop

| Phase | Artifact here | Produced by | Approved by |
|---|---|---|---|
| 1 Plan | [`intent.md`](../intent.md) | maintainer (with an agent drafting) | **maintainer — gate G1** |
| 2 Design | [`docs/spec/spec.md`](spec/spec.md) + 3 design docs + ADRs | agent drafts, maintainer reviews | **maintainer — gate G2** |
| 3 Build | [`plan.md`](../plan.md) | agent drafts from the spec | **maintainer — gate G3** |
| 4 Test | evals (M1 deliverable) + pytest/Vitest/Playwright | agent | CI |
| 5 Deploy | PR per [`REVIEW.md`](../REVIEW.md), then a Knative revision | agent + maintainer | agent review pass, then **maintainer — gate G4/G5** |
| 6 Maintain | incident → new `intent.md` | agent or maintainer | back to G1 |

## 2. Gates

| Gate | Question | Artifact | Signal that it passed |
|---|---|---|---|
| **G1** | Is this the right problem? | `intent.md` | `Status: accepted` |
| **G2** | Is this the right design? | `docs/spec/spec.md` | `Status: accepted` |
| **G3** | Is this the right work, in the right order? | `plan.md` | `- Status: Approved` |
| **G4** | Does the diff match the plan and the spec? | PR | review pass + green CI |
| **G5** | Should this go out? | Knative revision | maintainer deploys |

Two rules are not negotiable, because they are the difference between an agent
assistant and an agent deciding things:

1. **An agent may draft `intent.md` and `plan.md`, but may never approve G1, G3 or
   G5.** It can set `Status: Draft` and it can set `Status: Approved` only when the
   maintainer has said so in the same conversation.
2. **An agent never approves its own code.** G4's agent review pass produces
   findings; the maintainer's approval is still required to merge.

## 3. Why the plan gate is a script

The Build phase says "nothing is implemented without an accepted plan". A
convention in `AGENTS.md` is advice; an agent that touches an unexpected file has
not violated a *check*, only a suggestion. Two failures follow:

- **Silent scope creep.** The diff is locally reasonable, so review misses the
  extra file until it causes a problem.
- **Unverifiable claims.** "This matches the plan" is exactly the kind of thing an
  agent reports optimistically and a human cannot cheaply verify on a large diff.

The fix is to make the plan's claim **mechanical and small**: a bullet list of
paths/globs under `## Files that change`, compared against `git diff --name-only`
by [`scripts/check_plan_sync.py`](../scripts/check_plan_sync.py). The gate cannot
judge whether the plan is *good* — that is G3. It checks only **coverage**, and it
is the one thing a script can check better than a reviewer.

Adaptation from upstream (recorded in
[ADR-0006](spec/adr/0006-plan-sync-gate.md)): no `workflow-graph.yaml` and no
`gates/ledger.jsonl` — there is no second party to bind, so `- Status: Approved`
plus git history is the approval record.

**Cost:** `plan.md` must be current for each milestone. **Benefit:** a PR that
changes `app/` or `ui/` without declaring it fails CI with the exact paths.

### Working with the gate

```bash
# PR mode (what CI runs)
python scripts/check_plan_sync.py --base origin/main --head HEAD

# pre-commit hook (optional)
python scripts/check_plan_sync.py --hook
```

When it fails, either the work belongs in the plan or the work does not belong in
the change. Add the path to `## Files that change` in the same commit — never
widen the process-artifact list to make a failure disappear.

## 4. Process artifacts vs implementation

Exempt from the plan (updating docs never needs a plan): `docs/`, `intent.md`,
`plan.md`, `AGENTS.md`, `CLAUDE.md`, `REVIEW.md`, `README.md`, `LICENSE`,
`SECURITY.md`, `CHANGELOG.md`, `.github/`, `evals/`, `ui/SPEC.md`, the gate script
and its tests.

Everything else — `app/`, `ui/` (except `ui/SPEC.md`), `tests/`, `scripts/`,
`knative/` manifests, `data/`, `Dockerfile`, dependency files — needs a manifest
entry. `knative/README.md` **is** exempt (it is documentation, and punishing a doc
clarification is how docs rot); the manifests beside it are not, so deployment
changes are always planned.

## 5. Definition of done

A change is done when **all** of these are true in the same commit:

- [ ] Behavior matches the FR and the spec; deviations are in an ADR.
- [ ] Tests prove it, and the commands' output is pasted as evidence.
- [ ] `functional-design.md` and the `traceability.md` row are updated.
- [ ] `plan.md`'s manifest covers every changed implementation path.
- [ ] No secrets, no new unpinned dependencies, no edits made only to pass tests.
- [ ] The review checklist in `REVIEW.md` passes locally.

## 6. Cadence

| Trigger | Action |
|---|---|
| New idea or incident | draft `intent.md` → G1 |
| Intent accepted | draft/refresh spec → G2 |
| Spec accepted | write `plan.md` per milestone → G3 |
| Plan approved | implement in small commits; each updates docs and traceability |
| PR opened | plan gate + review pass; maintainer approves → G4 |
| Merged | deploy revision → G5; record what changed in `plan.md` |
| Same agent mistake twice | correction goes into `AGENTS.md` (not a chat message) |

## 7. Measurement (lightweight)

The upstream playbook measures cycle time and rework; a single maintainer needs
three numbers, recorded in `plan.md` per milestone:

- **Time from intent commit to spec commit** (are we over-thinking?).
- **Plan-gate failures per milestone** (are manifests being written honestly?).
- **Rework commits after a milestone claims done** (was "done" real?).

## 8. Anti-drift rules

1. One fact, one home. Everything else links.
2. Docs ride with code in the same commit.
3. ADRs are immutable; supersede, never edit.
4. IDs are permanent.
5. Prefer deleting a stale document over keeping a second source of truth.
6. When a rule matters, automate it (plan gate, CI) — otherwise it will erode.
