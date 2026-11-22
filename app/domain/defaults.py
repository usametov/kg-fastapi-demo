"""Known-good plans for the sample BOM data, for LLM-free demos and scripts.

These are what the L6/L7 agents typically converge to on the course data
(Product -> Assembly <- Part -> Supplier, plus review entities). They let you:
  * run `scripts/load_sample_data.py` without any API key, and
  * `PUT` a plan into a session to skip the LLM step during a demo.

NOTE: reconstructed for this demo, not copied from a notebook output cell.
"""

from app.domain.models import (
    ConstructionPlan,
    FactType,
    NodeConstruction,
    RelationshipConstruction,
    UnstructuredSchema,
    UserGoal,
)

DEFAULT_GOAL = UserGoal(
    kind_of_graph="supply chain analysis",
    description=(
        "A multi-level bill of materials for manufactured furniture products, used to trace "
        "customer-reported product issues back to assemblies, parts and suppliers (root-cause analysis)."
    ),
)

DEFAULT_FILES = [
    "products.csv",
    "assemblies.csv",
    "components.csv",
    "part_supplier_mapping.csv",
    "suppliers.csv",
]

DEFAULT_REVIEW_FILES = [
    "product_reviews/stockholm_chair_reviews.md",
    "product_reviews/gothenburg_table_reviews.md",
]

DEFAULT_PLAN = ConstructionPlan(
    rules={
        "Product": NodeConstruction(
            source_file="products.csv",
            label="Product",
            unique_column_name="product_id",
            properties=["product_name", "price", "description"],
        ),
        "Assembly": NodeConstruction(
            source_file="assemblies.csv",
            label="Assembly",
            unique_column_name="assembly_id",
            properties=["assembly_name", "component_name", "quantity"],
        ),
        "Part": NodeConstruction(
            source_file="components.csv",
            label="Part",
            unique_column_name="part_id",
            properties=["part_name", "sub_assembly_name", "quantity"],
        ),
        "Supplier": NodeConstruction(
            source_file="suppliers.csv",
            label="Supplier",
            unique_column_name="supplier_id",
            properties=["name", "specialty", "city", "country", "website", "contact_email"],
        ),
        "CONTAINS": RelationshipConstruction(
            source_file="assemblies.csv",
            relationship_type="CONTAINS",
            from_node_label="Product",
            from_node_column="product_id",
            to_node_label="Assembly",
            to_node_column="assembly_id",
        ),
        "IS_PART_OF": RelationshipConstruction(
            source_file="components.csv",
            relationship_type="IS_PART_OF",
            from_node_label="Part",
            from_node_column="part_id",
            to_node_label="Assembly",
            to_node_column="assembly_id",
        ),
        "SUPPLIED_BY": RelationshipConstruction(
            source_file="part_supplier_mapping.csv",
            relationship_type="SUPPLIED_BY",
            from_node_label="Part",
            from_node_column="part_id",
            to_node_label="Supplier",
            to_node_column="supplier_id",
            properties=["lead_time_days", "unit_cost", "minimum_order_quantity", "preferred_supplier"],
        ),
    }
)

DEFAULT_UNSTRUCTURED = UnstructuredSchema(
    entity_types=["Product", "Issue", "Feature"],
    fact_types=[
        FactType(subject_label="Product", predicate_label="has_issue", object_label="Issue"),
        FactType(subject_label="Product", predicate_label="includes_feature", object_label="Feature"),
    ],
)
