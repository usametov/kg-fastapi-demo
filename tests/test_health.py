def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "x-request-id" in r.headers


def test_ready_with_fakes(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["neo4j"] is True and r.json()["state_store"] is True


def test_docs_and_openapi(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/sessions", "/sessions/{session_id}/goal", "/sessions/{session_id}/files",
              "/sessions/{session_id}/schema/structured", "/sessions/{session_id}/schema/unstructured",
              "/sessions/{session_id}/build", "/jobs/{job_id}", "/query", "/health"]:
        assert p in paths
