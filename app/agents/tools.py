"""ADK function tools, borrowed from the notebooks (L4-L8).

ADK turns plain Python functions into LLM tools: the function *name*,
*docstring* and *type hints* become the tool schema the model sees, and a
parameter named `tool_context` is injected by ADK (not shown to the model).
`tool_context.state` is the shared session state; that's how one agent's
approved output becomes the next agent's input.

Why factories (`make_tools(files, graph)`) instead of module-level functions
like the notebooks? The notebooks close over a global `graphdb`; we close over
the injected FileCatalog/GraphDB so there are no globals and tests can pass
fakes. Tools only need an object with a `.state` dict, so unit tests can call
them with `SimpleNamespace(state={})` instead of a real ToolContext.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.domain import state_keys as K
from app.files import FileCatalog
from app.graph.cypher import PHYSICAL_SCHEMA
from app.graph.neo4j_client import GraphDB, is_write_query, tool_error, tool_success

# ToolContext is only used as a type hint; ADK needs to see the *name*
# `tool_context`. Keeping the import optional keeps this module importable in
# environments where ADK isn't installed (e.g. a slim worker image).
try:  # pragma: no cover
    from google.adk.tools import ToolContext
except Exception:  # pragma: no cover
    ToolContext = Any  # type: ignore[misc,assignment]

# Separate key so the L7 agents see the *review* files while L5/L6 see CSVs.
APPROVED_UNSTRUCTURED_FILES = "approved_unstructured_files"


def make_tools(files: FileCatalog, graph: GraphDB | None = None) -> SimpleNamespace:
    # ================================================================ L4
    def set_perceived_user_goal(kind_of_graph: str, graph_description: str, tool_context: ToolContext) -> dict:
        """Sets the perceived user's goal, including the kind of graph and its description.

        Args:
            kind_of_graph: at most 3 words describing the graph, for example "social network" or "USA freight logistics"
            graph_description: a few sentences about the intention of the graph
        """
        goal = {"kind_of_graph": kind_of_graph, "description": graph_description}
        tool_context.state[K.PERCEIVED_USER_GOAL] = goal
        return tool_success(K.PERCEIVED_USER_GOAL, goal)

    def approve_perceived_user_goal(tool_context: ToolContext) -> dict:
        """Upon approval from the user, records the perceived user goal as the approved user goal.

        Only call this tool if the user has explicitly approved the perceived user goal.
        """
        if K.PERCEIVED_USER_GOAL not in tool_context.state:
            return tool_error("perceived_user_goal not set. Set perceived user goal first, or ask clarifying questions if you are unsure.")
        tool_context.state[K.APPROVED_USER_GOAL] = tool_context.state[K.PERCEIVED_USER_GOAL]
        return tool_success(K.APPROVED_USER_GOAL, tool_context.state[K.APPROVED_USER_GOAL])

    def get_approved_user_goal(tool_context: ToolContext) -> dict:
        """Returns the user's goal, which is a dict containing the kind of graph and its description."""
        if K.APPROVED_USER_GOAL not in tool_context.state:
            return tool_error("approved_user_goal not set. Ask the user to clarify their goal (kind of graph and description).")
        return tool_success(K.APPROVED_USER_GOAL, tool_context.state[K.APPROVED_USER_GOAL])

    # ================================================================ L5
    def list_available_files(tool_context: ToolContext) -> dict:
        """Lists files available for knowledge graph construction.

        Returns a dict with 'status' and, on success, a 'files' list of relative paths.
        """
        return files.list_files()

    def sample_file(file_path: str, tool_context: ToolContext) -> dict:
        """Samples a file by reading its first lines (up to 100).

        Args:
            file_path: file to sample, relative to the import directory
        """
        return files.sample_file(file_path)

    def set_suggested_files(suggest_files: list[str], tool_context: ToolContext) -> dict:
        """Set the suggested files to be used for data import.

        Args:
            suggest_files: list of file paths to suggest
        """
        tool_context.state[K.SUGGESTED_FILES] = suggest_files
        return tool_success(K.SUGGESTED_FILES, suggest_files)

    def get_suggested_files(tool_context: ToolContext) -> dict:
        """Get the files to be used for data import."""
        return tool_success(K.SUGGESTED_FILES, tool_context.state.get(K.SUGGESTED_FILES, []))

    def approve_suggested_files(tool_context: ToolContext) -> dict:
        """Approves the suggested files for further processing as approved files.

        Only call this tool if the user has explicitly approved the suggested files.
        """
        if K.SUGGESTED_FILES not in tool_context.state:
            return tool_error("Current files have not been set. Take no action other than to inform user.")
        tool_context.state[K.APPROVED_FILES] = tool_context.state[K.SUGGESTED_FILES]
        return tool_success(K.APPROVED_FILES, tool_context.state[K.APPROVED_FILES])

    def get_approved_files(tool_context: ToolContext) -> dict:
        """Get the files that have been approved for import."""
        if K.APPROVED_FILES not in tool_context.state:
            return tool_error("approved files have not been set. Take no action other than to inform user.")
        return tool_success(K.APPROVED_FILES, tool_context.state[K.APPROVED_FILES])

    # ================================================================ L6
    def search_file(file_path: str, query: str, tool_context: ToolContext) -> dict:
        """Searches a file for lines containing the query string (case-insensitive).

        Useful for checking whether a suspected unique identifier really is unique.

        Args:
            file_path: file to search, relative to the import directory
            query: string to search for
        """
        return files.search_file(file_path, query)

    def get_proposed_construction_plan(tool_context: ToolContext) -> dict:
        """Get the proposed construction plan."""
        return tool_success(K.PROPOSED_CONSTRUCTION_PLAN, tool_context.state.get(K.PROPOSED_CONSTRUCTION_PLAN, {}))

    def propose_node_construction(approved_file: str, proposed_label: str, unique_column_name: str, proposed_properties: list[str], tool_context: ToolContext) -> dict:
        """Propose a node construction for an approved file that supports the user goal.

        The construction is added to the proposed construction plan under proposed_label.

        Args:
            approved_file: The approved file to propose a node construction for
            proposed_label: The proposed label for constructed nodes (used as key in the construction plan)
            unique_column_name: The column used to uniquely identify constructed nodes
            proposed_properties: Property names for the node, derived from column names in the approved file
        """
        # quick sanity check from the notebook: does the file have that column?
        found = files.search_file(approved_file, unique_column_name)
        if found["status"] == "error":
            return found
        if found["search_results"]["metadata"]["lines_found"] == 0:
            return tool_error(f"{approved_file} does not have the column {unique_column_name}. Check the file content and try again.")
        plan = dict(tool_context.state.get(K.PROPOSED_CONSTRUCTION_PLAN, {}))
        rule = {
            "construction_type": "node", "source_file": approved_file, "label": proposed_label,
            "unique_column_name": unique_column_name, "properties": proposed_properties,
        }
        plan[proposed_label] = rule
        tool_context.state[K.PROPOSED_CONSTRUCTION_PLAN] = plan  # reassign so ADK records the delta
        return tool_success("node_construction", rule)

    def propose_relationship_construction(approved_file: str, proposed_relationship_type: str, from_node_label: str, from_node_column: str, to_node_label: str, to_node_column: str, proposed_properties: list[str], tool_context: ToolContext) -> dict:
        """Propose a relationship construction for an approved file that supports the user goal.

        Args:
            approved_file: The approved file to propose a relationship construction for
            proposed_relationship_type: The proposed type for constructed relationships
            from_node_label: The label of the source node
            from_node_column: The column in the approved file that identifies source nodes
            to_node_label: The label of the target node
            to_node_column: The column in the approved file that identifies target nodes
            proposed_properties: Relationship property names, derived from columns in the approved file
        """
        for col, which in ((from_node_column, "from"), (to_node_column, "to")):
            found = files.search_file(approved_file, col)
            if found["status"] == "error":
                return found
            if found["search_results"]["metadata"]["lines_found"] == 0:
                return tool_error(f"{approved_file} does not have the {which} node column {col}. Check the content of the file and reconsider the relationship.")
        plan = dict(tool_context.state.get(K.PROPOSED_CONSTRUCTION_PLAN, {}))
        rule = {
            "construction_type": "relationship", "source_file": approved_file,
            "relationship_type": proposed_relationship_type,
            "from_node_label": from_node_label, "from_node_column": from_node_column,
            "to_node_label": to_node_label, "to_node_column": to_node_column,
            "properties": proposed_properties,
        }
        plan[proposed_relationship_type] = rule
        tool_context.state[K.PROPOSED_CONSTRUCTION_PLAN] = plan
        return tool_success("relationship_construction", rule)

    def remove_node_construction(node_label: str, tool_context: ToolContext) -> dict:
        """Remove a node construction from the proposed construction plan based on label.

        Args:
            node_label: The label of the node construction to remove
        """
        plan = dict(tool_context.state.get(K.PROPOSED_CONSTRUCTION_PLAN, {}))
        if node_label not in plan:
            return tool_success("message", "node construction rule not found. removal not needed.")
        del plan[node_label]
        tool_context.state[K.PROPOSED_CONSTRUCTION_PLAN] = plan
        return tool_success("node_construction_removed", node_label)

    def remove_relationship_construction(relationship_type: str, tool_context: ToolContext) -> dict:
        """Remove a relationship construction from the proposed construction plan based on type.

        Args:
            relationship_type: The type of the relationship construction to remove
        """
        plan = dict(tool_context.state.get(K.PROPOSED_CONSTRUCTION_PLAN, {}))
        if relationship_type not in plan:
            return tool_success("message", "relationship construction rule not found. removal not needed.")
        del plan[relationship_type]
        tool_context.state[K.PROPOSED_CONSTRUCTION_PLAN] = plan
        return tool_success("relationship_construction_removed", relationship_type)

    # ================================================================ L7
    def get_approved_unstructured_files(tool_context: ToolContext) -> dict:
        """Get the list of approved (unstructured, text/markdown) files to analyze."""
        approved = tool_context.state.get(APPROVED_UNSTRUCTURED_FILES)
        if not approved:
            return tool_error("approved files have not been set. Take no action other than to inform user.")
        return tool_success(K.APPROVED_FILES, approved)

    get_approved_unstructured_files.__name__ = "get_approved_files"  # prompt says 'get_approved_files'

    def get_well_known_types(tool_context: ToolContext) -> dict:
        """Gets the approved labels that represent well-known entity types in the graph schema."""
        plan = tool_context.state.get(K.APPROVED_CONSTRUCTION_PLAN, {})
        labels = sorted({r["label"] for r in plan.values() if r.get("construction_type") == "node"})
        return tool_success("approved_labels", labels)

    def set_proposed_entities(proposed_entity_types: list[str], tool_context: ToolContext) -> dict:
        """Sets the list of proposed entity types to extract from unstructured text.

        Args:
            proposed_entity_types: entity type names, e.g. ["Product", "Issue"]
        """
        tool_context.state[K.PROPOSED_ENTITIES] = proposed_entity_types
        return tool_success(K.PROPOSED_ENTITIES, proposed_entity_types)

    def get_proposed_entities(tool_context: ToolContext) -> dict:
        """Gets the list of proposed entity types to extract from unstructured text."""
        return tool_success(K.PROPOSED_ENTITIES, tool_context.state.get(K.PROPOSED_ENTITIES, []))

    def get_approved_entities(tool_context: ToolContext) -> dict:
        """Get the approved list of entity types to extract from unstructured text."""
        if K.APPROVED_ENTITIES not in tool_context.state:
            return tool_error("Approved entities have not been set. Take no further action.")
        return tool_success(K.APPROVED_ENTITIES, tool_context.state[K.APPROVED_ENTITIES])

    def add_proposed_fact(approved_subject_label: str, proposed_predicate_label: str, approved_object_label: str, tool_context: ToolContext) -> dict:
        """Add a proposed type of fact that could be extracted from the files.

        A proposed fact type is a tuple of (subject, predicate, object) where the
        subject and object are approved entity types and the predicate describes
        how they are related.

        Args:
            approved_subject_label: approved label of the subject entity type
            proposed_predicate_label: label of the predicate
            approved_object_label: approved label of the object entity type
        """
        approved = tool_context.state.get(K.APPROVED_ENTITIES, [])
        for lbl in (approved_subject_label, approved_object_label):
            if lbl not in approved:
                return tool_error(f"{lbl} is not an approved entity type. Only use approved entities: {approved}")
        facts = dict(tool_context.state.get(K.PROPOSED_FACTS, {}))
        facts[proposed_predicate_label] = {
            "subject_label": approved_subject_label,
            "predicate_label": proposed_predicate_label,
            "object_label": approved_object_label,
        }
        tool_context.state[K.PROPOSED_FACTS] = facts
        return tool_success(K.PROPOSED_FACTS, facts)

    def get_proposed_facts(tool_context: ToolContext) -> dict:
        """Get the proposed types of facts that could be extracted from the files."""
        return tool_success(K.PROPOSED_FACTS, tool_context.state.get(K.PROPOSED_FACTS, {}))

    # ============================================================ GraphRAG
    def get_physical_schema(tool_context: ToolContext) -> dict:
        """Get the physical schema of the graph: node labels and relationship types."""
        if graph is None:
            return tool_error("graph database not configured")
        return graph.send_query(PHYSICAL_SCHEMA, read_only=True)

    def read_neo4j_cypher(query: str, tool_context: ToolContext) -> dict:
        """Run a read-only Cypher query against the knowledge graph and return the records.

        Args:
            query: a read-only Cypher query (no CREATE/MERGE/SET/DELETE)
        """
        if graph is None:
            return tool_error("graph database not configured")
        if is_write_query(query):
            return tool_error("Write queries are not allowed. Use only read-only Cypher.")
        tool_context.state["last_cypher"] = query
        return graph.send_query(query, read_only=True)

    return SimpleNamespace(**{name: fn for name, fn in locals().items() if callable(fn) and not name.startswith("_")})
