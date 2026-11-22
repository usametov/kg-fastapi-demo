"""L8 part 2 - Lexical graph from review markdown + entity resolution.

Notebook: "KG construction" (second half). Uses neo4j-graphrag's
`SimpleKGPipeline`:
  * RegexTextSplitter("---") - each review in the .md files is separated by
    '---', so one chunk == one review (custom splitter from the notebook);
  * the approved L7 entity types / fact types become the extraction schema;
  * the pipeline writes Document/Chunk nodes, embeddings, and extracted
    `__Entity__` nodes + relationships.
Then `correlate_entities` links extracted entities (e.g. a Product mentioned in
a review) to the CSV-built domain nodes with CORRESPONDS_TO.

`pipeline_factory` is injectable so tests can replace the LLM pipeline.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Protocol

import anyio

from app.config import Settings
from app.domain.models import ConstructionPlan, UnstructuredSchema
from app.files import FileCatalog
from app.graph import cypher
from app.graph.neo4j_client import GraphDB


def to_rel_type(predicate: str) -> str:
    """'has issue' / 'hasIssue' -> 'HAS_ISSUE' (Neo4j relationship-type convention)."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", predicate.strip())
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()


class KGPipeline(Protocol):
    async def run_async(self, text: str, document_metadata: dict[str, Any] | None = None) -> Any: ...


def make_regex_splitter(pattern: str):
    """The notebook's RegexTextSplitter, as a neo4j-graphrag TextSplitter."""
    from app.construction.splitter import RegexTextSplitter

    return RegexTextSplitter(pattern)


def default_pipeline_factory(graph: GraphDB, settings: Settings, schema: UnstructuredSchema) -> KGPipeline:
    from neo4j_graphrag.embeddings import OpenAIEmbeddings
    from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
    from neo4j_graphrag.llm import OpenAILLM

    key = settings.openai_key()
    llm = OpenAILLM(
        model_name=settings.extraction_model,
        model_params={"temperature": 0, "response_format": {"type": "json_object"}},
        api_key=key,
    )
    embedder = OpenAIEmbeddings(model=settings.embedding_model, api_key=key)
    patterns = [(f.subject_label, to_rel_type(f.predicate_label), f.object_label) for f in schema.fact_types]
    return SimpleKGPipeline(
        llm=llm,
        driver=graph.driver,
        embedder=embedder,
        schema={
            "node_types": schema.entity_types,
            "relationship_types": sorted({p[1] for p in patterns}),
            "patterns": patterns,
        },
        from_file=False,
        text_splitter=make_regex_splitter(re.escape(settings.review_chunk_separator)),
        perform_entity_resolution=True,
        neo4j_database=graph.database,
    )


PipelineFactory = Callable[[GraphDB, Settings, UnstructuredSchema], KGPipeline]


async def construct_lexical_graph(
    graph: GraphDB,
    settings: Settings,
    files: FileCatalog,
    review_files: list[str],
    schema: UnstructuredSchema,
    plan: ConstructionPlan,
    report: Callable[[str], Awaitable[None]],
    pipeline_factory: PipelineFactory = default_pipeline_factory,
) -> dict[str, Any]:
    pipeline = pipeline_factory(graph, settings, schema)
    for path in review_files:
        text = files.read_text(path)
        await pipeline.run_async(text=text, document_metadata={"path": path})
        await report(f"lexical graph from {path}")

    # Entity resolution: well-known entity types that also exist as domain nodes.
    resolved: dict[str, Any] = {}
    for rule in plan.nodes:
        if rule.label not in schema.entity_types:
            continue
        domain_key = next((p for p in rule.properties if "name" in p.lower()), rule.unique_column_name)
        res = await anyio.to_thread.run_sync(
            cypher.correlate_entities, graph, rule.label, "name", rule.label, domain_key, settings.entity_similarity_threshold
        )
        resolved[rule.label] = res.get("query_result", res)
        await report(f"entity resolution :{rule.label}.name ~ {rule.label}.{domain_key}")
    return {"documents": review_files, "resolved": resolved}
