def test_read_cypher(client, fake_graph):
    r = client.post("/query", json={"cypher": "MATCH (n) RETURN count(n) AS n"})
    assert r.status_code == 200 and r.json()["records"] == fake_graph.rows


def test_write_cypher_rejected(client):
    for q in ["CREATE (n:X)", "MATCH (n) DETACH DELETE n", "MATCH (n) SET n.x = 1",
              'LOAD CSV FROM "file:///x.csv" AS row RETURN row']:
        assert client.post("/query", json={"cypher": q}).status_code == 400, q


def test_named_root_cause(client, fake_graph):
    r = client.post("/query", json={"named": "root_cause", "limit": 5})
    assert r.status_code == 200
    q, params = fake_graph.queries[-1]
    assert "SUPPLIED_BY" in q and params == {"limit": 5}


def test_question_uses_graphrag_agent(client):
    r = client.post("/query", json={"question": "How many products?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "There are 10 products."
    assert r.json()["cypher"].startswith("MATCH (p:Product)")


def test_exactly_one_mode(client):
    assert client.post("/query", json={}).status_code == 422
    assert client.post("/query", json={"cypher": "RETURN 1", "named": "graph_summary"}).status_code == 422
