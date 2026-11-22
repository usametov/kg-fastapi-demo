"""KG construction as a background job (L8) + job progress.

POST /sessions/{id}/build returns 202 Accepted immediately with a job id; the
client polls GET /jobs/{job_id}. Building can take minutes (LLM extraction per
review chunk), far longer than an HTTP request should stay open.

JOB_RUNNER=inprocess -> FastAPI BackgroundTasks (runs after the response is
sent, in this process). JOB_RUNNER=worker -> enqueue in Redis for
`python -m app.worker`. See app/construction/jobs.py for the tradeoffs.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, status

from app.construction.jobs import make_job_payload, run_build_job
from app.deps import FilesDep, GraphDep, SessionDep, SettingsDep, StoreDep
from app.domain.models import BuildRequest, Job, JobView

router = APIRouter(tags=["build"])


@router.post("/sessions/{session_id}/build", response_model=JobView, status_code=status.HTTP_202_ACCEPTED)
async def start_build(session: SessionDep, store: StoreDep, graph: GraphDep, files: FilesDep, settings: SettingsDep,
                      background: BackgroundTasks, body: BuildRequest = Body(default_factory=BuildRequest)) -> JobView:
    try:
        payload = make_job_payload(session, body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    job = Job(id=uuid.uuid4().hex, session_id=session.id, payload=payload)
    await store.save_job(job)
    if settings.job_runner == "worker":
        await store.enqueue_job(job.id)
    else:
        background.add_task(run_build_job, job.id, store, graph, files, settings)
    return JobView(**job.model_dump())


@router.get("/jobs/{job_id}", response_model=JobView)
async def get_job(job_id: str, store: StoreDep) -> JobView:
    job = await store.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} not found")
    return JobView(**job.model_dump())
