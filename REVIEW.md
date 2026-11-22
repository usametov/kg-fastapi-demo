# REVIEW.md — review policy

- **Status:** accepted
- **Date:** 2026-11-22
- **Applies to:** human review and the agent review pass (Phase 5 of
  [the playbook](docs/playbook.md))

Reviews are bidirectional: an agent reviews incoming PRs *and* addresses comments
on its own PRs. Findings never approve a PR; the maintainer's approval does.

## Severity

| Level | Definition | Effect |
|---|---|---|
| **Blocking** | Wrong behavior, security hole, data loss, secret exposure, a spec violation without an ADR, or a test edited to pass | Must be fixed before merge |
| **Important** | A real defect risk: missing error path, unhandled `None`, unbounded query, missing test for a new branch, docs left stale for changed behavior | Should be fixed; requires a reason if not |
| **Nit** | Naming, wording, formatting, comment clarity | Optional; **max 5 per review** |

If something is a Nit, say so explicitly. An unlabeled comment reads as Blocking.

## Cap and skip list

- **Maximum 5 nits per review.** Beyond that, summarize instead of enumerating.
- Do **not** comment on:
  - `ui/src/components/ai-elements/**` — vendored shadcn components; edit only
    when a behavior requires it.
  - Lockfiles, `requirements.txt` line order, generated files.
  - Formatting or lint that CI already enforces.
  - Doc wording, unless it is factually wrong or contradicts the spec.
  - The plan gate's own output — it either passes or it does not.

## Checklist (in order)

1. **Spec conformance** — does the diff implement the FR it claims? Any deviation
   recorded in an ADR?
2. **Plan conformance** — is every implementation path in `plan.md`'s manifest,
   and is `- Status: Approved` justified?
3. **Evidence** — are the test commands and their output shown? Does the output
   prove the claim, or just prove *something* ran?
4. **Security** — authz on new routes, `owner_id` filtering, no secret or prompt
   logging, read-only Cypher intact, no wildcard CORS with credentials.
5. **Error paths** — 409/422/502 shapes match
   [functional-design §6](docs/spec/functional-design.md#6-errors); no raw
   exception text reaches a user.
6. **Docs** — `functional-design.md` + the `traceability.md` row updated in the
   same commit.
7. **Dependencies** — pinned exactly; no new transitive surprise.
8. **Tests** — new behavior covered; no test weakened or deleted to pass.

## Evidence standard

Prefer a pasted command and its output over a description:

```
$ python3 -m unittest tests.test_check_plan_sync -v
Ran 8 tests … OK
$ python scripts/check_plan_sync.py --base origin/main --head HEAD
(no output, exit 0)
```

"Tested locally" without output is not evidence.

## Recurring findings

When the same finding appears a second time, it stops being a review comment and
becomes a rule in [`AGENTS.md`](AGENTS.md) — otherwise the third occurrence is a
process failure, not a code one.
