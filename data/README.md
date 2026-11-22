# Sample data

These files are the course's furniture bill-of-materials sample set
(products -> assemblies -> parts -> suppliers, plus product review markdown).

Source: copied from the course's public companion repo
[neo4j-contrib/agentic-kg](https://github.com/neo4j-contrib/agentic-kg) (`data/bom`, MIT License,
Copyright (c) 2025 Neo4j, Inc.). They match the data used in the DeepLearning.AI
"Agentic Knowledge Graph Construction" notebooks but were **not** extracted from your
downloaded notebooks (the notebooks reference these files in the Jupyter environment's
import directory; they don't embed them). If your course copy differs (e.g. a
`parts.csv` instead of `components.csv`), drop your files in here; the agents will
adapt, and only `app/domain/defaults.py` (the LLM-free demo plan) references file names.

| File | Becomes |
|---|---|
| products.csv | `(:Product {product_id})` |
| assemblies.csv | `(:Assembly {assembly_id})`, `(:Product)-[:CONTAINS]->(:Assembly)` |
| components.csv | `(:Part {part_id})`, `(:Part)-[:IS_PART_OF]->(:Assembly)` |
| suppliers.csv | `(:Supplier {supplier_id})` |
| part_supplier_mapping.csv | `(:Part)-[:SUPPLIED_BY]->(:Supplier)` |
| product_reviews/*.md | lexical graph: Document/Chunk + extracted Product/Issue/Feature entities |
