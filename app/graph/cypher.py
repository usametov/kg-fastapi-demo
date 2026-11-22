"""Cypher used across the app, borrowed from the notebooks (mostly L8).

Labels, relationship types and property keys are interpolated only after
`is_symbol()` validation; data values always go through $parameters.
Dynamic labels `$($label)` require Neo4j 5.26+ (compose uses neo4j:5.26).
"""

from __future__ import annotations

from typing import Any

from app.graph.neo4j_client import GraphDB, is_symbol, tool_error

# ---- L8: structured import ------------------------------------------------

def create_uniqueness_constraint(graph: GraphDB, label: str, unique_property_key: str) -> dict[str, Any]:
    """L8 `create_uniqueness_constraint`: speeds up MERGE and guarantees integrity."""
    if not (is_symbol(label) and is_symbol(unique_property_key)):
        return tool_error(f"invalid label/property: {label}.{unique_property_key}")
    name = f"{label}_{unique_property_key}_constraint"
    return graph.send_query(
        f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{unique_property_key} IS UNIQUE"
    )


def load_nodes_from_csv(graph: GraphDB, source_file: str, label: str, unique_column_name: str, properties: list[str]) -> dict[str, Any]:
    """L8 `load_nodes_from_csv`: batch MERGE nodes from a CSV in Neo4j's import dir."""
    if not is_symbol(unique_column_name):
        return tool_error(f"invalid column: {unique_column_name}")
    query = f"""LOAD CSV WITH HEADERS FROM "file:///" + $source_file AS row
    CALL (row) {{
        MERGE (n:$($label) {{ {unique_column_name} : row[$unique_column_name] }})
        FOREACH (k IN $properties | SET n[k] = row[k])
    }} IN TRANSACTIONS OF 1000 ROWS"""
    return graph.run_write(query, {
        "source_file": source_file, "label": label,
        "unique_column_name": unique_column_name, "properties": properties,
    })


def import_relationships(graph: GraphDB, rule: dict[str, Any]) -> dict[str, Any]:
    """L8 `import_relationships`: MATCH both ends by key, MERGE the relationship."""
    fc, tc = rule["from_node_column"], rule["to_node_column"]
    if not (is_symbol(fc) and is_symbol(tc)):
        return tool_error(f"invalid columns: {fc}, {tc}")
    query = f"""LOAD CSV WITH HEADERS FROM "file:///" + $source_file AS row
    CALL (row) {{
        MATCH (from_node:$($from_node_label) {{ {fc} : row[$from_node_column] }}),
              (to_node:$($to_node_label) {{ {tc} : row[$to_node_column] }})
        MERGE (from_node)-[r:$($relationship_type)]->(to_node)
        FOREACH (k IN $properties | SET r[k] = row[k])
    }} IN TRANSACTIONS OF 1000 ROWS"""
    return graph.run_write(query, {
        "source_file": rule["source_file"],
        "from_node_label": rule["from_node_label"], "from_node_column": fc,
        "to_node_label": rule["to_node_label"], "to_node_column": tc,
        "relationship_type": rule["relationship_type"], "properties": rule.get("properties", []),
    })


# ---- L8: entity resolution (lexical graph -> domain graph) ----------------

def correlate_entities(graph: GraphDB, entity_label: str, entity_key: str, domain_label: str, domain_key: str, threshold: float) -> dict[str, Any]:
    """L8 entity resolution: connect LLM-extracted entities to CSV-built nodes.

    SimpleKGPipeline labels extracted nodes `__Entity__` (plus e.g. `Product`),
    so we exclude `__Entity__` on the domain side. Matching uses APOC's
    Jaro-Winkler *distance* (0 = identical), as in the notebook.
    """
    if not all(is_symbol(s) for s in (entity_key, domain_key)):
        return tool_error("invalid key")
    query = f"""MATCH (entity:$($entity_label):__Entity__), (domain:$($domain_label))
    WHERE NOT domain:__Entity__
      AND entity.{entity_key} IS NOT NULL AND domain.{domain_key} IS NOT NULL
      AND apoc.text.jaroWinklerDistance(toLower(entity.{entity_key}), toLower(domain.{domain_key})) < $threshold
    MERGE (entity)-[r:CORRESPONDS_TO]->(domain)
    RETURN count(r) AS relationships_created"""
    return graph.send_query(query, {"entity_label": entity_label, "domain_label": domain_label, "threshold": threshold})


# ---- schema introspection (course: get_physical_schema) -------------------
PHYSICAL_SCHEMA = """CALL db.schema.visualization() YIELD nodes, relationships
RETURN [n IN nodes | labels(n)[0]] AS node_labels,
       [r IN relationships | type(r)] AS relationship_types"""

# ---- named queries for POST /query ----------------------------------------
NAMED_QUERIES: dict[str, str] = {
    "graph_summary": """MATCH (n) UNWIND labels(n) AS label
        RETURN label, count(*) AS count ORDER BY count DESC LIMIT $limit""",
    # The course's motivating question: which suppliers' parts end up in
    # products customers complain about? (domain graph + review lexical graph)
    "root_cause": """MATCH (e:__Entity__)-[:CORRESPONDS_TO]->(p:Product)
        MATCH (e)-[:HAS_ISSUE]->(i:Issue)
        MATCH (p)-[:CONTAINS]->(:Assembly)<-[:IS_PART_OF]-(part:Part)-[:SUPPLIED_BY]->(s:Supplier)
        RETURN p.product_name AS product,
               collect(DISTINCT i.name) AS issues,
               collect(DISTINCT s.name) AS suppliers
        ORDER BY size(issues) DESC LIMIT $limit""",
    "products_with_issues": """MATCH (e:__Entity__)-[:HAS_ISSUE]->(i:Issue)
        OPTIONAL MATCH (e)-[:CORRESPONDS_TO]->(p:Product)
        RETURN coalesce(p.product_name, e.name) AS product, collect(DISTINCT i.name) AS issues
        LIMIT $limit""",
}

RESET_GRAPH = "MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS"
