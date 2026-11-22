#!/usr/bin/env python3
"""Deterministic plan-sync enforcement (the plan gate).

Adopted from the AI-native SDLC playbook
(https://github.com/bashebr/ai-native-sdlc, skills/ai-native-sdlc/scripts/check_plan_sync.py).
It backs the "plan mode first" rule: an implementation change cannot pass a PR or
pre-commit check unless ``plan.md`` is Approved and its "Files that change"
manifest covers the changed paths. Departures from the plan must be declared in
``plan.md`` in the same change set.

Why a script and not a convention
---------------------------------
"This change matched the plan" is not a fact a reviewer can check cheaply on a
large diff, and an agent will not reliably self-report a departure. The manifest
is a small, mechanical claim, so the check is mechanical too: a bullet list of
paths/globs, compared against ``git diff --name-only``. It turns "we agreed on a
plan" into evidence that fails CI when it is no longer true.

Adapted from upstream: this repository has no ``workflow-graph.yaml`` and no
``gates/ledger.jsonl``, so the graph/ledger options are removed and ``- Status:
Approved`` in ``plan.md`` *is* the approval record (the commit is the audit
trail). Deliberately unchanged: process-artifact exemptions, three-dot diff,
manifest parsing, and the "entry added in the same change set" allowance.

Usage:
    scripts/check_plan_sync.py --base <rev> --head <rev> [--ignore GLOB]... [--two-dot]
    scripts/check_plan_sync.py --hook [--ignore GLOB]...

PR mode defaults to a three-dot diff (merge-base). Hook mode validates the
staged diff (HEAD vs index) and reads plan.md from the index.

Exit codes: 0 = pass, 1 = violation, 2 = usage error.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

# Paths that are process artifacts, not implementation. The checker never
# requires a plan for these; add more with --ignore. Keep this list narrow:
# anything that changes runtime behavior belongs under the plan.
PROCESS_ENTRIES = (
    "docs/",                    # spec, ADRs, playbook, vocabulary
    "evals/",                   # eval cases (M1 deliverable)
    ".github/",                 # CI
    "intent.md",                # phase 1 artifact
    "plan.md",                  # this gate's input
    "REVIEW.md",                # phase 5 policy
    "AGENTS.md",                # repo memory
    "CLAUDE.md",                # pointer to AGENTS.md
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CHANGELOG.md",
    "ui/SPEC.md",               # retired: pointer to docs/spec
    "scripts/check_plan_sync.py",
    "tests/test_check_plan_sync.py",
)

BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")


def _git(repo: Path, args: list[str]) -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, str(exc)
    if res.returncode != 0:
        return False, (res.stderr or res.stdout).strip()
    return True, res.stdout


def _is_process_path(path: str, ignores: list[str]) -> bool:
    if any(fnmatch.fnmatch(path, pattern) for pattern in ignores):
        return True
    normalized = path[2:] if path.startswith("./") else path
    for entry in PROCESS_ENTRIES:
        if entry.endswith("/"):
            if normalized == entry.rstrip("/") or normalized.startswith(entry):
                return True
        elif normalized == entry:
            return True
    return False


def _changed_files_pr(repo: Path, base: str, head: str, two_dot: bool) -> tuple[bool, list[str] | str]:
    sep = ".." if two_dot else "..."
    ok, out = _git(repo, ["diff", "--name-only", f"{base}{sep}{head}"])
    if not ok:
        return False, out
    return True, [line for line in out.splitlines() if line.strip()]


def _changed_files_hook(repo: Path) -> tuple[bool, list[str] | str]:
    ok, out = _git(repo, ["diff", "--cached", "--name-only"])
    if not ok:
        return False, out
    return True, [line for line in out.splitlines() if line.strip()]


def _show(repo: Path, spec: str) -> tuple[bool, str]:
    return _git(repo, ["show", f"{spec}:plan.md"])


def _manifest_entries(text: str) -> list[str]:
    """Parse the bullet list under '## Files that change'."""
    lines = text.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if line.strip().lower() == "## files that change":
            start = i
            break
    if start == -1:
        raise ValueError('plan.md has no "Files that change" section')

    section: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        section.append(line)

    bullets = [line for line in section if BULLET_RE.match(line)]
    if not bullets:
        raise ValueError('plan.md "Files that change" must be a bullet list of paths/globs')

    entries: list[str] = []
    for line in bullets:
        match = BULLET_RE.match(line)
        if match is None:  # pragma: no cover - bullets were filtered above
            continue
        entry = _normalize_entry(match.group(1))
        if entry and entry != "-":
            entries.append(entry)
    return entries


def _normalize_entry(entry: str) -> str:
    entry = entry.strip()
    if entry.startswith("`") and entry.endswith("`") and len(entry) > 1:
        entry = entry[1:-1]
    else:
        entry = entry.replace("`", "")
    entry = re.sub(r"\s+\((?:new|modified|deleted|renamed|added)\)\s*$", "", entry, flags=re.I)
    entry = re.sub(r"\s+(?:new|modified|deleted|renamed|added)\s*$", "", entry, flags=re.I)
    return entry.strip()


def _plan_is_approved(text: str) -> bool:
    """True when plan.md carries an approved status bullet.

    Accepts "- Status: Approved", "- **Status:** Approved" and the same with the
    value in bold: markdown emphasis is not a semantic difference, and rejecting
    it would fail the gate for a cosmetic reason.
    """
    for line in text.splitlines():
        if not line.strip().startswith(("-", "*")):
            continue
        if re.match(r"^\s*[-*]\s*status\s*:\s*approved\s*$", line.replace("*", ""), re.I):
            return True
    return False


def _added_manifest_entries(old_text: str | None, new_text: str) -> list[str]:
    """Entries added to the manifest by this change set.

    A path may be legitimately unplanned-as-of-base but declared in the same
    commit (the "update plan.md in the same change" rule). Only bullets added
    relative to the base plan count, so the manifest cannot be reworded into
    covering everything.
    """
    old_lines = (old_text or "").splitlines()
    new_lines = new_text.splitlines()
    try:
        old_entries = _manifest_entries("\n".join(old_lines)) if old_text is not None else []
    except ValueError:
        # Legacy plans may still be prose; migrating them to the bullet
        # manifest in the same change is supported. The head manifest is
        # authoritative, so treat the old manifest as empty.
        old_entries = []
    added: list[str] = []
    if old_entries:
        diff = difflib.unified_diff(old_lines, new_lines, lineterm="", n=0)
        for line in diff:
            if not line.startswith("+"):
                continue
            stripped = line[1:].strip()
            match = BULLET_RE.match(stripped)
            if not match:
                continue
            added.append(_normalize_entry(match.group(1)))
    else:
        added = _manifest_entries(new_text)
    return added


def _check(
    repo: Path,
    changed: list[str],
    plan_text: str | None,
    plan_diff_base: str | None,
    ignores: list[str],
) -> int:
    implementation = [path for path in changed if not _is_process_path(path, ignores)]
    if not implementation:
        return 0

    if plan_text is None:
        print("error: no plan.md", file=sys.stderr)
        return 1
    if not _plan_is_approved(plan_text):
        print(
            "error: plan.md is not approved - add a bullet '- Status: Approved' after the plan gate",
            file=sys.stderr,
        )
        return 1

    try:
        entries = _manifest_entries(plan_text)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Entries added to plan.md in this same change set also count.
    old_text = None
    if plan_diff_base is not None:
        ok, text = _show(repo, plan_diff_base)
        old_text = text if ok else None
    added = _added_manifest_entries(old_text, plan_text) if old_text is not None else []

    unplanned: list[str] = []
    for path in implementation:
        if any(fnmatch.fnmatch(path, entry) for entry in entries):
            continue
        if any(fnmatch.fnmatch(path, entry) for entry in added):
            continue
        unplanned.append(path)

    if unplanned:
        details = " ".join(
            f'{path} (add a matching entry under "Files that change" in plan.md)'
            for path in sorted(unplanned)
        )
        print(f"error: unplanned files: {details}", file=sys.stderr)
        return 1
    return 0


def cmd_pr(args: argparse.Namespace, repo: Path) -> int:
    ok, changed = _changed_files_pr(repo, args.base, args.head, args.two_dot)
    if not ok:
        print(f"error: git diff failed: {changed}", file=sys.stderr)
        return 1
    assert isinstance(changed, list)
    ok, head_plan = _show(repo, args.head)
    if not ok:
        head_plan = ""
    if not head_plan.strip():
        head_plan = None
    return _check(repo, changed, head_plan, args.base, args.ignore)


def cmd_hook(args: argparse.Namespace, repo: Path) -> int:
    ok, changed = _changed_files_hook(repo)
    if not ok:
        print(f"error: git diff failed: {changed}", file=sys.stderr)
        return 1
    assert isinstance(changed, list)
    ok, staged_plan = _show(repo, "")
    if not ok:
        staged_plan = ""
    if not staged_plan.strip():
        staged_plan = None
    if staged_plan is None:
        implementation = [path for path in changed if not _is_process_path(path, args.ignore)]
        if implementation:
            print(
                "error: plan.md is not staged; stage plan.md with the implementation",
                file=sys.stderr,
            )
            return 1
        return 0
    return _check(repo, changed, staged_plan, "HEAD", args.ignore)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", action="store_true", help="check the staged diff")
    parser.add_argument("--base", default=None, help="base revision (PR mode)")
    parser.add_argument("--head", default=None, help="head revision (PR mode)")
    parser.add_argument("--ignore", action="append", default=[], help="additional process-path glob")
    parser.add_argument(
        "--two-dot",
        action="store_true",
        help="use literal base..head instead of merge-base base...head",
    )
    args = parser.parse_args(argv)

    if args.hook and (args.base or args.head):
        parser.error("--hook cannot be combined with --base/--head")
    if not args.hook and not (args.base and args.head):
        parser.error("pass --hook or both --base and --head")

    repo = Path.cwd()
    if args.hook:
        return cmd_hook(args, repo)
    return cmd_pr(args, repo)


if __name__ == "__main__":
    raise SystemExit(main())
