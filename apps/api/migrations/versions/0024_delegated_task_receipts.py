"""Commit delegated operation receipts with Shopping effects and privacy fencing."""

import sqlalchemy as sa
from alembic import op

revision = "p9_delegated_task_receipts"
down_revision = "p9_conversation_generation_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delegated_task_receipts",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("execution_key", sa.Uuid(), nullable=False),
        sa.Column("intent_fingerprint", sa.String(64), nullable=False),
        sa.Column("target_entity_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("domain_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("owner_id", "execution_key"),
        sa.CheckConstraint(
            "intent_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_task_receipt_fingerprint"
        ),
        sa.CheckConstraint("state IN ('applied', 'rejected')", name="ck_task_receipt_state"),
        sa.CheckConstraint("domain_version >= 1", name="ck_task_receipt_domain_version"),
    )
    op.execute(
        "CREATE TRIGGER shopping_owner_write_guard BEFORE INSERT OR UPDATE "
        "ON delegated_task_receipts FOR EACH ROW EXECUTE FUNCTION shopping_guard_owner_write()"
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM delegated_task_receipts LIMIT 1")):
        raise RuntimeError("Cannot discard retained delegated task recovery state")
    op.drop_table("delegated_task_receipts")
