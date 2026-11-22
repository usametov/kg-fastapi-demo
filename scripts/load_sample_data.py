"""One-off admin process (Twelve-Factor XII): load the sample BOM graph.

Uses the *same* code and config as the API (app.construction), just without
the agents: it applies the known-good plan from app/domain/defaults.py.

    python -m scripts.load_sample_data                 # domain graph only, no LLM needed
    python -m scripts.load_sample_data --with-reviews  # + lexical graph (needs OPENAI_API_KEY)
    docker compose run --rm api python -m scripts.load_sample_data
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.config import get_settings
from app.construction.structured import construct_domain_graph
from app.construction.unstructured import construct_lexical_graph
from app.domain import defaults
from app.files import FileCatalog
from app.graph.neo4j_client import GraphDB
from app.logging_config import configure_logging

log = logging.getLogger("scripts.load_sample_data")


async def main(with_reviews: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    graph = GraphDB.from_settings(settings)
    try:
        result = construct_domain_graph(graph, defaults.DEFAULT_PLAN, lambda m: log.info(m))
        log.info("domain graph loaded", extra={"result": result})
        if with_reviews:
            async def report(m: str) -> None:
                log.info(m)

            res = await construct_lexical_graph(
                graph, settings, FileCatalog(settings.data_dir), defaults.DEFAULT_REVIEW_FILES,
                defaults.DEFAULT_UNSTRUCTURED, defaults.DEFAULT_PLAN, report,
            )
            log.info("lexical graph loaded", extra={"result": res})
    finally:
        graph.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--with-reviews", action="store_true")
    asyncio.run(main(p.parse_args().with_reviews))
