# ADR-0006: Adopt a deterministic plan gate (`check_plan_sync.py`)

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** Alan Samet
- **Related:** [playbook §Why the plan gate is a script](../../playbook.md#3-why-the-plan-gate-is-a-script), `scripts/check_plan_sync.py`

## Context

The playbook's Build phase requires "nothing is implemented without an accepted
plan". With agents doing most of the editing, two failure modes appear:

1. **Silent scope creep** — the agent touches files the approved plan never
   mentioned, and the diff looks locally reasonable so review misses it.
2. **Unverifiable claims** — "this matches the plan" is a judgment a reviewer
   cannot make cheaply on a large diff, and agents self-report optimistically.

Conventions alone (a sentence in `AGENTS.md`) are advisory. The playbook's rule is
only as strong as its enforcement.

## Decision

Adopt the playbook's `check_plan_sync.py`, adapted to this repo:

- Upstream location: `skills/ai-native-sdlc/scripts/check_plan_sync.py`
  (bashebr/ai-native-sdlc). Kept: three-dot diff, `## Files that change` bullet
  manifest, `- Status: Approved` requirement, process-artifact exemptions, and
  the allowance for entries added in the same change set.
- Removed: `workflow-graph.yaml` and `gates/ledger.jsonl` integration. This repo
  has no workflow graph or gate ledger, and adding one for a single maintainer
  would be ceremony without a second party to bind.
- `- Status: Approved` **is** the approval record; git history is the audit trail.
- Process artifacts are exempt (`docs/`, `intent.md`, `plan.md`, `AGENTS.md`,
  `REVIEW.md`, `.github/`, `evals/`, `ui/SPEC.md`, the gate and its tests).

Enforcement points: PRs via `.github/workflows/plan-sync.yml`, and optionally a
pre-commit hook (`--hook` mode).

## Consequences

- A PR that changes `app/` or `ui/` without a matching manifest entry **fails
  CI**, with the exact unplanned paths printed.
- Changing the plan to match the work is allowed — but the change must be in the
  same commit, so the deviation is visible rather than silent.
- The gate is not a reviewer: it checks *coverage*, not whether the plan is good.
  G3 (human approval) still decides that.
- `plan.md` must be kept current per milestone, which is the intended cost.
- Friction is real for pure refactors; the escape hatch is an honest manifest
  entry, not an exemption list that grows.
- The gate has no secret-scanning or test-running role; those remain separate.

## Alternatives rejected

| Option | Why not |
|---|---|
| **Convention only (`AGENTS.md`)** | Advisory; exactly the failure mode above |
| **Required PR template checkbox** | Self-attested, unverifiable, trivially ticked |
| **Full upstream setup (graph + ledger)** | Solves multi-party governance we do not have; two extra artifacts to maintain |
| **CI path filters / CODEOWNERS** | Route reviewers, do not compare a diff against a declared plan |

## References

- Upstream: https://github.com/bashebr/ai-native-sdlc
- `tests/test_check_plan_sync.py` (8 tests, stdlib only)
