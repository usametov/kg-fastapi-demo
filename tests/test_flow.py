"""End-to-end API flow with the fake LLM + fake Neo4j (L4 -> L8)."""

import time


def _wait_job(client, job_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_full_agentic_flow(client, fake_graph):
    sid = client.post("/sessions").json()["id"]

    # L4: chat, then approve via chat keyword
    r = client.post(f"/sessions/{sid}/goal", json={"message": "root cause of product issues"})
    assert r.status_code == 200 and "perceived_user_goal" in r.json()["state"]
    assert "approved_user_goal" not in r.json()["state"]
    r = client.post(f"/sessions/{sid}/goal/approve")
    assert r.json()["kind_of_graph"] == "supply chain analysis"
    # history kept across stateless requests
    assert len(client.get(f"/sessions/{sid}").json()["state"]) >= 2

    # L5
    r = client.post(f"/sessions/{sid}/files", json={})
    assert "products.csv" in r.json()["state"]["suggested_files"]
    assert client.post(f"/sessions/{sid}/files/approve").status_code == 200

    # L6
    r = client.post(f"/sessions/{sid}/schema/structured", json={"feedback": ""})
    body = r.json()
    assert body["proposed"]["Product"]["construction_type"] == "node"
    assert body["critic_feedback"] == "valid"
    assert client.post(f"/sessions/{sid}/schema/structured/approve").json()["approved"] is True

    # L7 (two-phase, like the notebook)
    r = client.post(f"/sessions/{sid}/schema/unstructured", json={"phase": "entities"})
    assert r.json()["proposed"]["entity_types"] == ["Product", "Issue"]
    assert client.post(f"/sessions/{sid}/schema/unstructured", json={"phase": "facts"}).status_code == 409
    client.post(f"/sessions/{sid}/schema/unstructured/approve-entities")
    r = client.post(f"/sessions/{sid}/schema/unstructured", json={"phase": "facts"})
    assert r.json()["proposed"]["fact_types"][0]["predicate_label"] == "has_issue"
    assert client.post(f"/sessions/{sid}/schema/unstructured/approve").json()["approved"] is not None

    # L8: structured-only build in the background
    r = client.post(f"/sessions/{sid}/build", json={"include_unstructured": False})
    assert r.status_code == 202
    job = _wait_job(client, r.json()["id"])
    assert job["status"] == "succeeded", job
    assert job["progress"] == 1.0
    cypher = "\n".join(q for q, _ in fake_graph.queries)
    assert "CREATE CONSTRAINT Product_product_id_constraint" in cypher
    assert "LOAD CSV WITH HEADERS" in cypher


def test_preconditions_enforced(client):
    sid = client.post("/sessions").json()["id"]
    assert client.post(f"/sessions/{sid}/files", json={}).status_code == 409
    assert client.post(f"/sessions/{sid}/schema/structured", json={}).status_code == 409
    assert client.post(f"/sessions/{sid}/build", json={}).status_code == 409
    assert client.get("/sessions/nope").status_code == 404
    assert client.get("/jobs/nope").status_code == 404


def test_manual_defaults_path(client):
    """PUT endpoints let a demo skip the LLM entirely."""
    sid = client.post("/sessions").json()["id"]
    client.put(f"/sessions/{sid}/goal", json={"kind_of_graph": "bom", "description": "x"})
    assert client.put(f"/sessions/{sid}/files", json={"files": ["nope.csv"]}).status_code == 422
    assert client.put(f"/sessions/{sid}/files", json={"files": ["products.csv"]}).status_code == 200
    r = client.put(f"/sessions/{sid}/schema/structured?use_default=true")
    assert set(r.json()["proposed"]) >= {"Product", "Assembly", "Part", "Supplier", "SUPPLIED_BY"}
    r = client.put(f"/sessions/{sid}/schema/unstructured?use_default=true")
    assert r.json()["approved"]["entity_types"] == ["Product", "Issue", "Feature"]
