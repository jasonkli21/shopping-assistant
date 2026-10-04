"""Add canonical catalog identity while retaining Phase 3 observations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_catalog_normalization"
down_revision: str | None = "0005_bounded_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(300), nullable=False),
        sa.Column("brand", sa.String(200), nullable=True),
        sa.Column("brand_key", sa.String(200), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("model_family", sa.String(200), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(btrim(canonical_name)) BETWEEN 1 AND 300", name="ck_product_name"
        ),
        sa.CheckConstraint("brand IS NULL OR char_length(brand) <= 200", name="ck_product_brand"),
        sa.CheckConstraint(
            "category IS NULL OR char_length(category) <= 100", name="ck_product_category"
        ),
        sa.CheckConstraint(
            "model_family IS NULL OR char_length(model_family) <= 200",
            name="ck_product_model_family",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_product_revision"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_owner_name", "products", ["owner_id", "canonical_name"])

    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("identity_key", sa.String(500), nullable=False),
        sa.Column("identity_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("category_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(btrim(display_name)) BETWEEN 1 AND 300", name="ck_variant_name"
        ),
        sa.CheckConstraint(
            "char_length(identity_key) BETWEEN 1 AND 500", name="ck_variant_identity_key"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_variant_revision"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "identity_key", name="uq_variant_product_identity"),
    )
    op.create_index("ix_variants_product", "product_variants", ["product_id", "created_at"])

    op.create_table(
        "catalog_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("requested_url", sa.String(2048), nullable=False),
        sa.Column("final_url", sa.String(2048), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("content_type", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("extractor_version", sa.String(80), nullable=False),
        sa.Column("task_version", sa.String(80), nullable=False),
        sa.Column("extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excerpts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("failure_code", sa.String(60), nullable=True),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'blocked', 'unsupported')",
            name="ck_catalog_observation_status",
        ),
        sa.CheckConstraint(
            "char_length(requested_url) <= 2048 AND char_length(final_url) <= 2048",
            name="ck_catalog_observation_urls",
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_observation_hash",
        ),
        sa.CheckConstraint(
            "char_length(extractor_version) BETWEEN 1 AND 80", name="ck_catalog_extractor_version"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["discovery_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "idempotency_key", name="uq_catalog_observation_candidate_key"
        ),
    )
    op.create_index(
        "ix_catalog_observations_candidate_time",
        "catalog_observations",
        ["candidate_id", "retrieved_at"],
    )

    op.create_table(
        "product_identifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("scheme", sa.String(32), nullable=False),
        sa.Column("namespace", sa.String(300), nullable=False),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("normalized_value", sa.String(200), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "scheme IN ('manufacturer_model', 'gtin', 'mpn', 'retailer_sku')",
            name="ck_identifier_scheme",
        ),
        sa.CheckConstraint(
            "char_length(btrim(value)) BETWEEN 1 AND 200", name="ck_identifier_value"
        ),
        sa.CheckConstraint(
            "char_length(namespace) BETWEEN 1 AND 300", name="ck_identifier_namespace"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["catalog_observations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "variant_id",
            "scheme",
            "namespace",
            "normalized_value",
            name="uq_identifier_variant_key",
        ),
    )
    op.create_index(
        "ix_identifiers_lookup", "product_identifiers", ["scheme", "namespace", "normalized_value"]
    )

    op.create_table(
        "project_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("first_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("first_run_id", sa.Uuid(), nullable=True),
        sa.Column("discovery_reason", sa.String(300), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(discovery_reason) <= 300", name="ck_project_product_reason"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["first_run_id"], ["research_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "variant_id", name="uq_project_product_project_variant"),
    )
    op.create_index(
        "ix_project_products_project_created",
        "project_products",
        ["project_id", "created_at", "id"],
    )
    op.create_foreign_key(
        "fk_project_products_first_candidate",
        "project_products",
        "discovery_candidates",
        ["first_candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_discovery_candidate_canonical_mapping",
        "discovery_candidates",
        "project_products",
        ["canonical_mapping_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "retail_offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("retailer_name", sa.String(200), nullable=False),
        sa.Column("retailer_domain", sa.String(253), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("availability", sa.String(16), nullable=False),
        sa.Column("condition", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(amount IS NULL AND currency IS NULL) OR (amount >= 0 AND currency ~ '^[A-Z]{3}$')",
            name="ck_offer_amount_currency",
        ),
        sa.CheckConstraint(
            "availability IN ('in_stock', 'out_of_stock', 'preorder', 'unknown')",
            name="ck_offer_availability",
        ),
        sa.CheckConstraint(
            "condition IN ('new', 'used', 'refurbished', 'unknown')", name="ck_offer_condition"
        ),
        sa.CheckConstraint(
            "char_length(retailer_name) BETWEEN 1 AND 200", name="ck_offer_retailer_name"
        ),
        sa.CheckConstraint("char_length(url) BETWEEN 1 AND 2048", name="ck_offer_url"),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["catalog_observations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_offer_owner_idempotency"),
    )
    op.create_index(
        "ix_offers_variant_observed", "retail_offers", ["variant_id", sa.text("observed_at DESC")]
    )

    op.create_table(
        "entity_resolution_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("previous_project_product_id", sa.Uuid(), nullable=True),
        sa.Column("selected_project_product_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_event_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('auto_linked', 'manual_linked', 'unresolved', 'reverted')",
            name="ck_resolution_event_status",
        ),
        sa.CheckConstraint("actor IN ('system', 'owner')", name="ck_resolution_actor"),
        sa.ForeignKeyConstraint(["project_id"], ["shopping_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["discovery_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["catalog_observations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["previous_project_product_id"], ["project_products.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["selected_project_product_id"], ["project_products.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reversed_event_id"], ["entity_resolution_events.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "project_id",
            "candidate_id",
            "request_key",
            name="uq_resolution_request_key",
        ),
    )
    op.create_index(
        "ix_resolution_candidate_time", "entity_resolution_events", ["candidate_id", "created_at"]
    )


def downgrade() -> None:
    # Phase 3 discovery candidates and candidate_search_results remain intact.
    op.execute("UPDATE discovery_candidates SET canonical_mapping_id = NULL")
    op.drop_index("ix_resolution_candidate_time", table_name="entity_resolution_events")
    op.drop_table("entity_resolution_events")
    op.drop_index("ix_offers_variant_observed", table_name="retail_offers")
    op.drop_table("retail_offers")
    op.drop_constraint(
        "fk_discovery_candidate_canonical_mapping", "discovery_candidates", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_project_products_first_candidate", "project_products", type_="foreignkey"
    )
    op.drop_index("ix_project_products_project_created", table_name="project_products")
    op.drop_table("project_products")
    op.drop_index("ix_identifiers_lookup", table_name="product_identifiers")
    op.drop_table("product_identifiers")
    op.drop_index("ix_catalog_observations_candidate_time", table_name="catalog_observations")
    op.drop_table("catalog_observations")
    op.drop_index("ix_variants_product", table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_index("ix_products_owner_name", table_name="products")
    op.drop_table("products")
