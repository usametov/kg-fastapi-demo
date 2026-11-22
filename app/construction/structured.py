"""L8 part 1 - Build the *domain graph* from CSVs using the approved L6 plan.

Notebook: "KG construction". Order matters, exactly as in the notebook's
`construct_domain_graph`:
    1. for every node rule: uniqueness constraint, then LOAD CSV + MERGE nodes
    2. for every relationship rule: LOAD CSV + MATCH ends + MERGE relationship
"""

from __future__ import annotations

from typing import Any, Callable

from app.domain.models import ConstructionPlan
from app.graph import cypher
from app.graph.neo4j_client import GraphDB


def construct_domain_graph(graph: GraphDB, plan: ConstructionPlan, report: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    errors: list[str] = []
    for rule in plan.nodes:
        res = cypher.create_uniqueness_constraint(graph, rule.label, rule.unique_column_name)
        if res["status"] == "error":
            errors.append(f"constraint {rule.label}: {res['error_message']}")
        props = list(dict.fromkeys([rule.unique_column_name, *rule.properties]))
        res = cypher.load_nodes_from_csv(graph, rule.source_file, rule.label, rule.unique_column_name, props)
        if res["status"] == "error":
            errors.append(f"nodes {rule.label}: {res['error_message']}")
        report(f"nodes :{rule.label} from {rule.source_file}")
    for rule in plan.relationships:
        res = cypher.import_relationships(graph, rule.model_dump())
        if res["status"] == "error":
            errors.append(f"rel {rule.relationship_type}: {res['error_message']}")
        report(f"relationships :{rule.relationship_type} from {rule.source_file}")
    return {"nodes": [r.label for r in plan.nodes], "relationships": [r.relationship_type for r in plan.relationships], "errors": errors}
