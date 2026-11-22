"""Query the finished knowledge graph.

POST /query accepts exactly one of:
  * cypher   - raw read-only Cypher (write clauses rejected with 400; executed
               with READ routing). Use a read-only Neo4j user in production.
  * named    - a vetted query from app/graph/cypher.py NAMED_QUERIES, incl.
               the course's root-cause question (suppliers behind product issues)
  * question - natural language -> GraphRAG agent (text-to-Cypher via LLM)
"""

from __future__ import annotations

import re

import anyio
from fastapi import APIRouter, HTTPException

from app.deps import GraphDep, RunnerDep
from app.domain.models import QueryRequest, QueryResponse
from app.graph.cypher import NAMED_QUERIES
from app.graph.neo4j_client import is_write_query

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, graph: GraphDep, runner: RunnerDep) -> QueryResponse:
    modes = [m for m in ("cypher", "named", "question") if getattr(body, m)]
    if len(modes) != 1:
        raise HTTPException(422, "set exactly one of: cypher, named, question")
    mode = modes[0]

    if mode == "question":
        try:
            result = await runner.run("graphrag", body.question, {}, None)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"graphrag agent failed: {exc}") from exc
        cy = result.state.get("last_cypher")
        if not cy:
            m = re.search(r"CYPHER:\s*(.+)", result.reply, re.S)
            cy = m.group(1).strip() if m else None
        return QueryResponse(mode=mode, cypher=cy, answer=result.reply)

    if mode == "cypher":
        cy, params = body.cypher, dict(body.params)
        if is_write_query(cy):
            raise HTTPException(400, "write queries are not allowed on /query")
    else:
        cy, params = NAMED_QUERIES[body.named], {"limit": body.limit}

    res = await anyio.to_thread.run_sync(lambda: graph.send_query(cy, params, read_only=True))
    if res["status"] == "error":
        raise HTTPException(400, res["error_message"])
    return QueryResponse(mode=mode, cypher=cy, records=res["query_result"])
