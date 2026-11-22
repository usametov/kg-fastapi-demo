"""`python -m app.worker` - background build worker (Factor VIII: concurrency).

Run as a separate process type when JOB_RUNNER=worker and STATE_BACKEND=redis.
It BRPOPs job ids from Redis and runs `run_build_job`. Scale it out by running
more replicas (`docker compose up --scale worker=3`).

Graceful shutdown (Factor IX): on SIGTERM/SIGINT we stop taking new jobs,
let the current job finish, then close the Neo4j driver and Redis pool.
A job interrupted by SIGKILL stays 'running'; a production version would use a
reliable queue (e.g. RQ/Arq/Celery or Redis Streams with ack) to re-deliver it.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.config import get_settings
from app.construction.jobs import run_build_job
from app.files import FileCatalog
from app.graph.neo4j_client import GraphDB
from app.logging_config import configure_logging
from app.state.factory import build_state_store

logger = logging.getLogger("app.worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.state_backend != "redis":
        raise SystemExit("worker requires STATE_BACKEND=redis (memory state is per-process)")
    store = build_state_store(settings)
    graph = GraphDB.from_settings(settings)
    files = FileCatalog(settings.data_dir)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    logger.info("worker started", extra={"redis": settings.redis_url})
    try:
        while not stop.is_set():
            job_id = await store.dequeue_job(timeout=2)
            if job_id:
                logger.info("job picked up", extra={"job_id": job_id})
                await run_build_job(job_id, store, graph, files, settings)
    finally:
        await store.close()
        graph.close()
        logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
