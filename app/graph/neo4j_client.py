"""Neo4j wrapper, adapted from the course helper `neo4j_for_adk.py`.

The notebooks import `from neo4j_for_adk import graphdb` - a module-level
singleton whose `send_query()` returns ADK-friendly dicts:
    {"status": "success", "query_result": [...]}  or
    {"status": "error", "error_message": "..."}
Agents read those dicts as tool results, so we keep the same contract.

Differences from the notebook helper:
  * no global singleton: one `GraphDB` is created in the FastAPI lifespan and
    handed out through dependency injection (app/deps.py), so tests can swap in
    a fake and the driver is closed on shutdown (Factor IX: disposability);
  * config comes from Settings (NEO4J_URI etc.) instead of os.getenv.

That helper is NOT shipped in the notebooks you downloaded (it lives in the
course's Jupyter file browser); this file reimplements it from the public
companion repo github.com/neo4j-contrib/agentic-kg (MIT).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from neo4j import Driver, GraphDatabase

logger = logging.getLogger(__name__)


# ---- tool_result helpers (course: tool_success / tool_error) --------------
def tool_success(key: str, result: Any) -> dict[str, Any]:
    return {"status": "success", key: result}


def tool_error(message: str) -> dict[str, Any]:
    return {"status": "error", "error_message": message}


# ---- safety helpers (course: is_write_query / is_symbol) ------------------
_WRITE_RE = re.compile(r"\b(MERGE|CREATE|SET|DELETE|REMOVE|DETACH|DROP|LOAD\s+CSV|FOREACH|CALL\s+apoc\.(?!meta|text))\b", re.I)
_CYPHER_KEYWORDS = {
    "MATCH", "RETURN", "WHERE", "CREATE", "DELETE", "REMOVE", "SET", "ORDER", "BY", "SKIP", "LIMIT",
    "MERGE", "ON", "OPTIONAL", "DETACH", "WITH", "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END",
    "AS", "UNION", "ALL", "LOAD", "CSV", "FROM", "START", "YIELD", "CALL", "CONSTRAINT", "ASSERT",
    "INDEX", "UNIQUE", "DROP", "EXISTS", "USING", "PERIODIC", "COMMIT", "FOREACH", "TRUE", "FALSE",
    "NULL", "NOT", "AND", "OR", "XOR", "IS", "IN", "STARTS", "ENDS", "CONTAINS",
}
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_write_query(query: str) -> bool:
    """True if the Cypher looks like it writes. Used to keep /query read-only.

    The course version only checked MERGE|CREATE|SET|DELETE|REMOVE|ADD; we
    also block DETACH/DROP/LOAD CSV/FOREACH and most APOC procedures. This is
    a guard-rail, not a security boundary: in production also connect /query
    with a *read-only Neo4j user* (or use a READ access-mode session, as below).
    """
    return _WRITE_RE.search(query) is not None


def is_symbol(symbol: str) -> bool:
    """Valid label / property / rel-type identifier (not a keyword, no spaces).

    Labels and property keys can't be Cypher parameters in some clauses
    (e.g. CREATE CONSTRAINT), so we validate before string-interpolating.
    """
    return bool(_SYMBOL_RE.match(symbol)) and symbol.upper() not in _CYPHER_KEYWORDS


def to_python(value: Any) -> Any:
    """Convert neo4j Node/Relationship/Path/temporal types into JSON-able data."""
    import neo4j.time
    from neo4j.graph import Node, Path, Relationship

    if isinstance(value, dict):
        return {k: to_python(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_python(v) for v in value]
    if isinstance(value, Node):
        return {"labels": sorted(value.labels), "properties": to_python(dict(value))}
    if isinstance(value, Relationship):
        return {"type": value.type, "properties": to_python(dict(value))}
    if isinstance(value, Path):
        return {"nodes": [to_python(n) for n in value.nodes], "relationships": [to_python(r) for r in value.relationships]}
    if isinstance(value, (neo4j.time.DateTime, neo4j.time.Date, neo4j.time.Time, neo4j.time.Duration)):
        return str(value)
    return value


class GraphDB:
    """Thin wrapper around a neo4j `Driver` with the course's send_query contract."""

    def __init__(self, driver: Driver, database: str = "neo4j") -> None:
        self.driver = driver
        self.database = database

    @classmethod
    def from_settings(cls, settings) -> "GraphDB":
        # GraphDatabase.driver() is lazy: it doesn't open a socket until the
        # first query, so API startup stays fast even if Neo4j is still booting.
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
        )
        return cls(driver, settings.neo4j_database)

    def send_query(self, cypher: str, parameters: dict[str, Any] | None = None, *, read_only: bool = False) -> dict[str, Any]:
        """Run Cypher; return {"status": "success", "query_result": [...]} or an error dict.

        Errors are returned (not raised) because LLM tools should *see* the
        error message and self-correct - that's how the notebooks behave.
        """
        try:
            kwargs: dict[str, Any] = {"database_": self.database}
            if read_only:
                from neo4j import RoutingControl

                kwargs["routing_"] = RoutingControl.READ
            records, _, _ = self.driver.execute_query(cypher, parameters or {}, **kwargs)
            return tool_success("query_result", [to_python(r.data()) for r in records])
        except Exception as exc:  # noqa: BLE001 - surfaced to the agent/user
            logger.warning("cypher failed", extra={"error": str(exc), "cypher": cypher[:200]})
            return tool_error(str(exc))

    def run_write(self, cypher: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run Cypher in an *implicit* (auto-commit) transaction.

        Needed for `CALL {...} IN TRANSACTIONS` (used by the L8 CSV import),
        which Neo4j refuses inside the managed transactions of execute_query.
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(cypher, parameters or {})
                return tool_success("query_result", [to_python(r.data()) for r in result])
        except Exception as exc:  # noqa: BLE001
            logger.warning("cypher write failed", extra={"error": str(exc), "cypher": cypher[:200]})
            return tool_error(str(exc))

    def verify(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    def close(self) -> None:
        self.driver.close()
