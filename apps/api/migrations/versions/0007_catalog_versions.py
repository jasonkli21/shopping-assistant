"""Add catalog-wide revisioning and exact catalog-command replay hashes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_catalog_versions"
down_revision: str | None = "0006_catalog_normalization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_catalog_state",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 1", name="ck_owner_catalog_revision"),
        sa.PrimaryKeyConstraint("owner_id"),
    )
    op.execute(
        "INSERT INTO owner_catalog_state (owner_id) "
        "SELECT owner_id FROM products UNION SELECT owner_id FROM retail_offers "
        "UNION SELECT owner_id FROM catalog_observations "
        "UNION SELECT owner_id FROM entity_resolution_events"
    )

    op.add_column("catalog_observations", sa.Column("request_hash", sa.String(64), nullable=True))
    op.execute(
        "UPDATE catalog_observations SET request_hash = "
        "md5(idempotency_key) || md5('catalog:' || idempotency_key)"
    )
    op.alter_column("catalog_observations", "request_hash", nullable=False)
    op.create_check_constraint(
        "ck_catalog_observation_request_hash",
        "catalog_observations",
        "request_hash ~ '^[0-9a-f]{64}$'",
    )

    op.add_column(
        "entity_resolution_events", sa.Column("request_hash", sa.String(64), nullable=True)
    )
    op.execute(
        "UPDATE entity_resolution_events SET request_hash = "
        "md5(request_key) || md5('resolution:' || request_key)"
    )
    op.alter_column("entity_resolution_events", "request_hash", nullable=False)
    op.add_column(
        "entity_resolution_events", sa.Column("command_type", sa.String(24), nullable=True)
    )
    op.execute(
        "UPDATE entity_resolution_events SET command_type = CASE "
        "WHEN actor = 'owner' AND status = 'reverted' THEN 'revert' "
        "WHEN actor = 'owner' THEN 'correction' ELSE 'normalize' END"
    )
    op.alter_column("entity_resolution_events", "command_type", nullable=False)
    op.create_check_constraint(
        "ck_resolution_command_type",
        "entity_resolution_events",
        "command_type IN ('normalize', 'correction', 'revert')",
    )
    op.drop_constraint("uq_resolution_request_key", "entity_resolution_events", type_="unique")
    op.create_unique_constraint(
        "uq_resolution_request_key",
        "entity_resolution_events",
        ["owner_id", "project_id", "command_type", "request_key"],
    )
    op.create_check_constraint(
        "ck_resolution_request_hash",
        "entity_resolution_events",
        "request_hash ~ '^[0-9a-f]{64}$'",
    )
    op.add_column(
        "entity_resolution_events",
        sa.Column("catalog_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "entity_resolution_events",
        sa.Column("project_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_resolution_catalog_version", "entity_resolution_events", "catalog_version >= 1"
    )
    op.create_check_constraint(
        "ck_resolution_project_version", "entity_resolution_events", "project_version >= 1"
    )
    op.create_check_constraint(
        "ck_variant_identity_attributes_size",
        "product_variants",
        "jsonb_typeof(identity_attributes) = 'object' AND "
        "octet_length(identity_attributes::text) <= 12000",
    )
    op.create_check_constraint(
        "ck_variant_category_attributes_size",
        "product_variants",
        "jsonb_typeof(category_attributes) = 'object' AND "
        "octet_length(category_attributes::text) <= 12000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_variant_category_attributes_size", "product_variants", type_="check")
    op.drop_constraint("ck_variant_identity_attributes_size", "product_variants", type_="check")
    op.drop_constraint("ck_resolution_project_version", "entity_resolution_events", type_="check")
    op.drop_constraint("ck_resolution_catalog_version", "entity_resolution_events", type_="check")
    op.drop_constraint("uq_resolution_request_key", "entity_resolution_events", type_="unique")
    op.create_unique_constraint(
        "uq_resolution_request_key",
        "entity_resolution_events",
        ["owner_id", "project_id", "candidate_id", "request_key"],
    )
    op.drop_constraint("ck_resolution_command_type", "entity_resolution_events", type_="check")
    op.drop_column("entity_resolution_events", "command_type")
    op.drop_column("entity_resolution_events", "project_version")
    op.drop_column("entity_resolution_events", "catalog_version")
    op.drop_constraint("ck_resolution_request_hash", "entity_resolution_events", type_="check")
    op.drop_column("entity_resolution_events", "request_hash")
    op.drop_constraint("ck_catalog_observation_request_hash", "catalog_observations", type_="check")
    op.drop_column("catalog_observations", "request_hash")
    op.drop_table("owner_catalog_state")
