"""StateStore implementations + the build job (fake pipeline, fake Neo4j)."""

import asyncio

import fakeredis.aioredis
import pytest

from app.construction.jobs import make_job_payload, run_build_job
from app.domain import defaults
from app.domain.models import BuildRequest, Job, JobStatus
from app.files import FileCatalog
from app.state.base import SessionRecord
from app.state.memory import MemoryStateStore
from app.state.redis_store import RedisStateStore


@pytest.fixture(params=["memory", "redis"])
def store(request):
    if request.param == "memory":
        return MemoryStateStore()
    return RedisStateStore(fakeredis.aioredis.FakeRedis(decode_responses=True), ttl_seconds=60)


def test_store_roundtrip_and_queue(store):
    async def go():
        s = await store.create_session()
        s.state["x"] = 1
        await store.save_session(s)
        assert (await store.get_session(s.id)).state == {"x": 1}
        assert await store.get_session("missing") is None
        job = Job(id="j1", session_id=s.id)
        await store.save_job(job)
        assert (await store.get_job("j1")).status == JobStatus.queued
        await store.enqueue_job("j1")
        assert await store.dequeue_job(timeout=1) == "j1"
        assert await store.ping()

    asyncio.run(go())


class FakePipeline:
    def __init__(self):
        self.texts = []

    async def run_async(self, text, document_metadata=None):
        self.texts.append((document_metadata or {}).get("path"))


def _session_with_defaults():
    s = SessionRecord()
    s.state.update({
        "approved_construction_plan": defaults.DEFAULT_PLAN.to_state(),
        "approved_entity_types": defaults.DEFAULT_UNSTRUCTURED.entity_types,
        "approved_fact_types": {f.predicate_label: f.model_dump() for f in defaults.DEFAULT_UNSTRUCTURED.fact_types},
        "approved_unstructured_files": defaults.DEFAULT_REVIEW_FILES,
    })
    return s


def test_build_job_full(settings, fake_graph):
    pipeline = FakePipeline()

    async def go():
        store = MemoryStateStore()
        s = _session_with_defaults()
        job = Job(id="b1", session_id=s.id, payload=make_job_payload(s, BuildRequest(reset_graph=True)))
        await store.save_job(job)
        await run_build_job("b1", store, fake_graph, FileCatalog(settings.data_dir), settings,
                            pipeline_factory=lambda g, st, sc: pipeline)
        return await store.get_job("b1")

    job = asyncio.run(go())
    assert job.status == JobStatus.succeeded, job.error
    assert pipeline.texts == defaults.DEFAULT_REVIEW_FILES
    joined = "\n".join(q for q, _ in fake_graph.queries)
    assert "DETACH DELETE" in joined and "CORRESPONDS_TO" in joined and "jaroWinklerDistance" in joined
    assert job.steps[-1] == "done" and job.progress == 1.0


def test_build_job_failure_is_recorded(settings, fake_graph):
    class Boom:
        async def run_async(self, text, document_metadata=None):
            raise RuntimeError("llm down")

    async def go():
        store = MemoryStateStore()
        s = _session_with_defaults()
        job = Job(id="b2", session_id=s.id, payload=make_job_payload(s, BuildRequest(include_structured=False)))
        await store.save_job(job)
        await run_build_job("b2", store, fake_graph, FileCatalog(settings.data_dir), settings,
                            pipeline_factory=lambda g, st, sc: Boom())
        return await store.get_job("b2")

    job = asyncio.run(go())
    assert job.status == JobStatus.failed and "llm down" in job.error


def test_worker_mode_enqueues(client, settings):
    settings.job_runner = "worker"
    sid = client.post("/sessions").json()["id"]
    client.put(f"/sessions/{sid}/schema/structured?use_default=true")
    r = client.post(f"/sessions/{sid}/build", json={"include_unstructured": False})
    assert r.status_code == 202 and r.json()["status"] == "queued"
    store = client.app.state.store
    assert asyncio.run(store.dequeue_job(timeout=1)) == r.json()["id"]
