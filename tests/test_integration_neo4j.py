"""Optional integration test against a REAL Neo4j (no LLM needed).

Skipped unless RUN_NEO4J_IT=1. Neo4j must have APOC and its import dir must
point at ./data (docker compose does both):

    docker compose up -d neo4j
    RUN_NEO4J_IT=1 NEO4J_PASSWORD=please-change-me pytest -q tests/test_integration_neo4j.py
"""

import os

import pytest

from app.config import Settings
from app.construction.structured import construct_domain_graph
from app.domain.defaults import DEFAULT_PLAN
from app.graph import cypher
from app.graph.neo4j_client import GraphDB

pytestmark = pytest.mark.skipif(os.getenv("RUN_NEO4J_IT") != "1", reason="set RUN_NEO4J_IT=1 to run")


def test_domain_graph_and_root_cause_on_real_neo4j():
    g = GraphDB.from_settings(Settings())
    try:
        assert g.verify()
        g.run_write(cypher.RESET_GRAPH)
        result = construct_domain_graph(g, DEFAULT_PLAN)
        assert result["errors"] == []
        counts = {r["l"]: r["c"] for r in g.send_query("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS c")["query_result"]}
        assert counts == {"Product": 10, "Assembly": 64, "Part": 88, "Supplier": 20}
        # simulate one LLM-extracted review entity, then resolve + ask the root-cause question
        g.send_query('CREATE (:__Entity__:Product {name:"Stockholm chair"})-[:HAS_ISSUE]->(:__Entity__:Issue {name:"squeaking"})')
        res = cypher.correlate_entities(g, "Product", "name", "Product", "product_name", 0.1)
        assert res["query_result"][0]["relationships_created"] == 1
        rows = g.send_query(cypher.NAMED_QUERIES["root_cause"], {"limit": 5})["query_result"]
        assert rows[0]["product"] == "Stockholm Chair" and rows[0]["issues"] == ["squeaking"] and rows[0]["suppliers"]
    finally:
        g.run_write(cypher.RESET_GRAPH)
        g.close()
