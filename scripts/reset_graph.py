"""One-off admin process (Twelve-Factor XII): wipe the graph and constraints.

    python -m scripts.reset_graph --yes
    docker compose run --rm api python -m scripts.reset_graph --yes
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.config import get_settings
from app.graph.cypher import RESET_GRAPH
from app.graph.neo4j_client import GraphDB, is_symbol
from app.logging_config import configure_logging

log = logging.getLogger("scripts.reset_graph")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--yes", action="store_true", help="really delete everything")
    p.add_argument("--keep-constraints", action="store_true")
    args = p.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    if not args.yes:
        log.error("refusing to reset without --yes", extra={"neo4j": settings.neo4j_uri})
        return 2
    graph = GraphDB.from_settings(settings)
    try:
        res = graph.run_write(RESET_GRAPH)
        if res["status"] == "error":
            log.error("reset failed", extra={"error": res["error_message"]})
            return 1
        if not args.keep_constraints:
            names = graph.send_query("SHOW CONSTRAINTS YIELD name RETURN name").get("query_result", [])
            for row in names:
                if is_symbol(row["name"]):
                    graph.send_query(f"DROP CONSTRAINT {row['name']} IF EXISTS")
        log.info("graph reset", extra={"neo4j": settings.neo4j_uri})
        return 0
    finally:
        graph.close()


if __name__ == "__main__":
    sys.exit(main())
