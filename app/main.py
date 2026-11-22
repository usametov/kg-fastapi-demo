"""FastAPI application factory + lifespan.

Run locally:   uvicorn app.main:app --reload --port $PORT
In Docker:     python -m app   (reads HOST/PORT from env; Factor VII)

Lifespan (Factor IX: disposability):
  * startup is fast - nothing blocks on Neo4j/Redis/LLM; drivers connect
    lazily and readiness is reported by GET /health/ready;
  * on SIGTERM uvicorn stops accepting requests, finishes in-flight ones,
    then the code after `yield` closes the Neo4j driver and Redis pool.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app import __version__
from app.agents.runner import AdkAgentRunner
from app.config import Settings, get_settings
from app.files import FileCatalog
from app.graph.neo4j_client import GraphDB
from app.logging_config import configure_logging
from app.routers import build, health, query, schema, sessions
from app.state.factory import build_state_store

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ---- startup: create attached-resource clients (no network I/O yet)
        app.state.settings = settings
        app.state.graph = GraphDB.from_settings(settings)
        app.state.store = build_state_store(settings)
        app.state.files = FileCatalog(settings.data_dir)
        app.state.runner = AdkAgentRunner(settings, app.state.files, app.state.graph)
        logger.info(
            "startup",
            extra={"env": settings.environment, "state_backend": settings.state_backend,
                   "job_runner": settings.job_runner, "neo4j": settings.neo4j_uri, "llm": settings.llm_model},
        )
        yield
        # ---- shutdown: release resources gracefully
        await app.state.store.close()
        app.state.graph.close()
        logger.info("shutdown complete")

    app = FastAPI(
        title="Agentic KG Construction API",
        version=__version__,
        description="FastAPI wrapper around the DeepLearning.AI 'Agentic Knowledge Graph Construction' notebooks.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        """One structured JSON log line per request, with a request id."""
        rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        logger.info("request", extra={"rid": rid, "method": request.method, "path": request.url.path,
                                      "status": response.status_code, "ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

    # Routers keep each lesson's endpoints in their own module.
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(schema.router)
    app.include_router(build.router)
    app.include_router(query.router)
    return app


app = create_app()
