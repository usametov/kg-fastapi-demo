"""Unit tests for the notebook-borrowed tools and helpers (no LLM)."""

from types import SimpleNamespace

from app.agents.tools import make_tools
from app.construction.unstructured import to_rel_type
from app.files import FileCatalog
from app.graph.neo4j_client import is_symbol, is_write_query


def test_file_catalog(settings):
    fc = FileCatalog(settings.data_dir)
    files = fc.list_files()["files"]
    assert "products.csv" in files and any(f.endswith(".md") for f in files)
    assert fc.sample_file("products.csv")["content"].startswith("product_name")
    assert fc.search_file("products.csv", "P-1000")["search_results"]["metadata"]["lines_found"] == 1
    assert fc.sample_file("../../etc/passwd")["status"] == "error"  # path traversal blocked


def test_goal_tools_require_order(settings):
    t = make_tools(FileCatalog(settings.data_dir))
    ctx = SimpleNamespace(state={})
    assert t.approve_perceived_user_goal(ctx)["status"] == "error"
    t.set_perceived_user_goal("bom", "desc", ctx)
    assert t.approve_perceived_user_goal(ctx)["status"] == "success"
    assert ctx.state["approved_user_goal"]["kind_of_graph"] == "bom"


def test_node_construction_checks_column(settings):
    t = make_tools(FileCatalog(settings.data_dir))
    ctx = SimpleNamespace(state={})
    assert t.propose_node_construction("products.csv", "Product", "no_such_col", [], ctx)["status"] == "error"
    assert t.propose_relationship_construction(
        "part_supplier_mapping.csv", "SUPPLIED_BY", "Part", "part_id", "Supplier", "supplier_id", [], ctx
    )["status"] == "success"
    assert t.remove_relationship_construction("SUPPLIED_BY", ctx)["status"] == "success"
    assert ctx.state["proposed_construction_plan"] == {}


def test_fact_requires_approved_entities(settings):
    t = make_tools(FileCatalog(settings.data_dir))
    ctx = SimpleNamespace(state={"approved_entity_types": ["Product", "Issue"]})
    assert t.add_proposed_fact("Product", "has_issue", "Issue", ctx)["status"] == "success"
    assert t.add_proposed_fact("Product", "made_in", "Country", ctx)["status"] == "error"


def test_tool_names_match_prompts(settings):
    t = make_tools(FileCatalog(settings.data_dir))
    assert t.get_approved_unstructured_files.__name__ == "get_approved_files"


def test_helpers():
    assert is_write_query("merge (n)") and not is_write_query("MATCH (n) RETURN n")
    assert is_symbol("Product") and not is_symbol("MATCH") and not is_symbol("a b") and not is_symbol("x}) DETACH")
    assert to_rel_type("has issue") == "HAS_ISSUE" and to_rel_type("includesFeature") == "INCLUDES_FEATURE"


def test_regex_splitter_one_review_per_chunk(settings):
    import asyncio

    from app.construction.unstructured import make_regex_splitter

    text = FileCatalog(settings.data_dir).read_text("product_reviews/stockholm_chair_reviews.md")
    chunks = asyncio.run(make_regex_splitter("---").run(text)).chunks
    assert len(chunks) == text.count("---") + 1
    assert all("Rating" in c.text for c in chunks)
