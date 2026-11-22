"""The build job: run L8 construction and report progress into the StateStore.

Same coroutine for both concurrency modes (Factor VIII):
  * JOB_RUNNER=inprocess - scheduled with FastAPI `BackgroundTasks` right after
    the 202 response is sent. Simple, but the work shares the API's CPU and is
    lost if the pod restarts mid-build.
  * JOB_RUNNER=worker    - the API only enqueues the job id in Redis;
    `python -m app.worker` (separate process / container / Deployment) dequeues
    and calls this function. Scales independently, survives API restarts.
The job carries a *snapshot* of the approved plans in its payload, so the
worker doesn't depend on the session still being around.
"""

from __future__ import annotations

import logging
from typing import Any

import anyio

from app.config import Settings
from app.construction.structured import construct_domain_graph
from app.construction.unstructured import PipelineFactory, construct_lexical_graph, default_pipeline_factory
from app.domain import state_keys as K
from app.domain.models import BuildRequest, ConstructionPlan, Job, JobStatus, UnstructuredSchema
from app.files import FileCatalog
from app.graph import cypher
from app.graph.neo4j_client import GraphDB
from app.state.base import SessionRecord, StateStore

logger = logging.getLogger(__name__)
REVIEW_FILES_KEY = "approved_unstructured_files"


def make_job_payload(session: SessionRecord, req: BuildRequest) -> dict[str, Any]:
    """Validate the session has what the build needs and snapshot it."""
    s = session.state
    if req.include_structured and not s.get(K.APPROVED_CONSTRUCTION_PLAN):
        raise ValueError("approved_construction_plan missing: run/approve /schema/structured first")
    if req.include_unstructured and not (s.get(K.APPROVED_ENTITIES) and s.get(REVIEW_FILES_KEY)):
        raise ValueError("approved entity types / review files missing: run/approve /schema/unstructured first")
    facts = s.get(K.APPROVED_FACTS, {})
    return {
        "request": req.model_dump(),
        "plan": s.get(K.APPROVED_CONSTRUCTION_PLAN, {}),
        "unstructured": {
            "entity_types": s.get(K.APPROVED_ENTITIES, []),
            "fact_types": list(facts.values()) if isinstance(facts, dict) else facts,
        },
        "review_files": s.get(REVIEW_FILES_KEY, []),
    }


async def run_build_job(
    job_id: str,
    store: StateStore,
    graph: GraphDB,
    files: FileCatalog,
    settings: Settings,
    pipeline_factory: PipelineFactory = default_pipeline_factory,
) -> None:
    job = await store.get_job(job_id)
    if job is None:
        logger.error("job not found", extra={"job_id": job_id})
        return
    log_extra = {"job_id": job.id, "session_id": job.session_id}
    req = BuildRequest(**job.payload["request"])
    plan = ConstructionPlan.from_state(job.payload["plan"])
    schema = UnstructuredSchema(**job.payload["unstructured"])
    total = 1 + int(req.reset_graph) + len(plan.rules) * int(req.include_structured) + (
        (len(job.payload["review_files"]) + len(schema.entity_types)) * int(req.include_unstructured)
    )
    done = 0

    async def report(msg: str) -> None:
        nonlocal done
        done += 1
        job.steps.append(msg)
        job.progress = round(min(done / total, 0.99), 3)
        await store.save_job(job)
        logger.info("build step", extra={**log_extra, "step": msg, "progress": job.progress})

    job.status = JobStatus.running
    await store.save_job(job)
    try:
        result: dict[str, Any] = {}
        if req.reset_graph:
            await anyio.to_thread.run_sync(graph.run_write, cypher.RESET_GRAPH)
            await report("graph reset")
        if req.include_structured:
            # The neo4j driver is sync (like the notebooks), so run it in a
            # worker thread to keep the event loop responsive.
            steps: list[str] = []
            result["domain_graph"] = await anyio.to_thread.run_sync(construct_domain_graph, graph, plan, steps.append)
            for s in steps:
                await report(s)
        if req.include_unstructured:
            result["lexical_graph"] = await construct_lexical_graph(
                graph, settings, files, job.payload["review_files"], schema, plan, report, pipeline_factory
            )
        job.result = result
        job.status = JobStatus.succeeded
        job.progress = 1.0
        job.steps.append("done")
    except Exception as exc:  # noqa: BLE001 - recorded on the job for the client
        logger.exception("build failed", extra=log_extra)
        job.status = JobStatus.failed
        job.error = f"{type(exc).__name__}: {exc}"
    await store.save_job(job)
