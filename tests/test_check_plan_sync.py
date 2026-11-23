"""Tests for scripts/check_plan_sync.py (the plan gate).

Stdlib-only (unittest) so the gate can be verified with a bare Python: no venv,
no dependencies. pytest collects these classes too.

Each test builds a throwaway git repo in a temp dir: the gate is defined by what
`git diff` sees, so exercising it against real commits is the only honest check.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_plan_sync.py"

APPROVED_PLAN = """\
# Plan: test

- Status: Approved
- Gate: G3

## Files that change

{entries}

## Proof

- unit tests
"""

DRAFT_PLAN = APPROVED_PLAN.replace("- Status: Approved", "- Status: Draft")


def plan(entries: list[str], approved: bool = True) -> str:
    body = APPROVED_PLAN if approved else DRAFT_PLAN
    return body.format(entries="\n".join(f"- `{e}`" for e in entries) if entries else "")


class GitRepo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "Test")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True, capture_output=True, text=True,
        ).stdout

    def write(self, rel: str, content: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content))

    def commit(self, msg: str = "change") -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD").strip()

    def check(self, base: str, head: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base", base, "--head", head],
            cwd=self.root, capture_output=True, text=True,
        )


class PlanSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = GitRepo(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _base(self, entries: list[str], approved: bool = True) -> str:
        self.repo.write("plan.md", plan(entries, approved))
        self.repo.write("app/main.py", "x = 1\n")
        return self.repo.commit("base")

    def test_planned_change_passes(self) -> None:
        base = self._base(["app/main.py"])
        self.repo.write("app/main.py", "x = 2\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_unplanned_change_fails(self) -> None:
        base = self._base(["app/main.py"])
        self.repo.write("app/other.py", "y = 1\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 1)
        self.assertIn("unplanned files", res.stderr)
        self.assertIn("app/other.py", res.stderr)

    def test_process_only_change_passes_without_approval(self) -> None:
        base = self._base(["app/main.py"], approved=False)
        self.repo.write("docs/spec/functional-design.md", "# edit\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_draft_plan_blocks_implementation(self) -> None:
        base = self._base(["app/main.py"], approved=False)
        self.repo.write("app/main.py", "x = 3\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 1)
        self.assertIn("not approved", res.stderr)

    def test_missing_manifest_section_fails(self) -> None:
        self.repo.write("plan.md", "# Plan\n\n- Status: Approved\n")
        self.repo.write("app/main.py", "x = 1\n")
        base = self.repo.commit("base")
        self.repo.write("app/main.py", "x = 2\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 1)
        self.assertIn("Files that change", res.stderr)

    def test_entry_added_in_same_change_set_counts(self) -> None:
        base = self._base(["app/main.py"])
        self.repo.write("plan.md", plan(["app/main.py", "app/new.py"]))
        self.repo.write("app/new.py", "z = 1\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_glob_covers_nested_paths(self) -> None:
        base = self._base(["ui/**"])
        self.repo.write("ui/src/components/App.tsx", "export {}\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_dotfile_process_path_is_exempt(self) -> None:
        base = self._base(["app/main.py"], approved=False)
        self.repo.write(".github/workflows/ci.yml", "name: ci\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_bold_status_is_accepted(self) -> None:
        base = self._base(["app/main.py"])
        self.repo.write("plan.md", plan(["app/main.py"]).replace(
            "- Status: Approved", "- **Status:** Approved"))
        head = self.repo.commit()
        self.repo.write("app/main.py", "x = 4\n")
        head = self.repo.commit()
        res = self.repo.check(base, head)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_knative_readme_exempt_but_manifests_are_not(self) -> None:
        base = self._base(["app/main.py"])
        self.repo.write("knative/README.md", "# docs edit\n")
        head = self.repo.commit()
        self.assertEqual(self.repo.check(base, head).returncode, 0)

        self.repo.write("knative/service.yaml", "kind: Service\n")
        head2 = self.repo.commit()
        res = self.repo.check(head, head2)
        self.assertEqual(res.returncode, 1)
        self.assertIn("knative/service.yaml", res.stderr)

    def test_staging_without_plan_fails_in_hook_mode(self) -> None:
        base = self._base(["app/main.py"])
        self.repo.write("app/other.py", "y = 1\n")
        self.repo.git("add", "app/other.py")
        res = subprocess.run(
            [sys.executable, str(SCRIPT), "--hook"],
            cwd=self.repo.root, capture_output=True, text=True,
        )
        self.assertNotEqual(base, "")
        self.assertEqual(res.returncode, 1)
        self.assertIn("unplanned files", res.stderr)


if __name__ == "__main__":
    unittest.main()
