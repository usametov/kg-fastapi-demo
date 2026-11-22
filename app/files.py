"""File tools over DATA_DIR, borrowed from L5 (file suggestion) and L6.

Notebook tools: `list_available_files`, `sample_file`, `search_file`. In the
course they look in the Neo4j import directory (found via
`CALL dbms.listConfig('server.directories.import')`). Here the API reads the
same files from DATA_DIR, which docker-compose mounts at both /app/data (API)
and /import (Neo4j), so `LOAD CSV "file:///products.csv"` sees what the agent saw.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.graph.neo4j_client import tool_error, tool_success

ALLOWED_SUFFIXES = {".csv", ".md", ".txt", ".json"}


class FileCatalog:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir).resolve()

    def _resolve(self, relative: str) -> Path | None:
        """Resolve a path inside DATA_DIR; refuse traversal like '../../etc/passwd'."""
        p = (self.root / relative).resolve()
        return p if p.is_file() and self.root in p.parents else None

    def list_files(self) -> dict[str, Any]:
        """L5 `list_available_files`: every importable file, relative to DATA_DIR."""
        if not self.root.is_dir():
            return tool_error(f"data dir {self.root} not found")
        files = sorted(
            str(p.relative_to(self.root))
            for p in self.root.rglob("*")
            if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES and not p.name.startswith(".")
        )
        return tool_success("files", files)

    def sample_file(self, file_path: str, max_lines: int = 100) -> dict[str, Any]:
        """L5 `sample_file`: first N lines so the LLM can judge relevance/structure."""
        p = self._resolve(file_path)
        if p is None:
            return tool_error(f"file not found: {file_path}")
        with p.open(encoding="utf-8", errors="replace") as fh:
            lines = [next(fh, None) for _ in range(max_lines)]
        return tool_success("content", "".join(l for l in lines if l is not None))

    def search_file(self, file_path: str, query: str) -> dict[str, Any]:
        """L6 `search_file`: case-insensitive grep; used to check id uniqueness."""
        p = self._resolve(file_path)
        if p is None:
            return tool_error(f"file not found: {file_path}")
        q = query.lower()
        matches = [
            {"line_number": i, "content": line.rstrip("\n")}
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(True), 1)
            if q in line.lower()
        ]
        return tool_success(
            "search_results",
            {"metadata": {"path": file_path, "query": query, "lines_found": len(matches)}, "matching_lines": matches[:200]},
        )

    def read_text(self, file_path: str) -> str:
        p = self._resolve(file_path)
        if p is None:
            raise FileNotFoundError(file_path)
        return p.read_text(encoding="utf-8")
