"""Record the UTC application time for project proposals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_proposal_applied_at"
down_revision: str | None = "0003_conversations_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_update_proposals",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE project_update_proposals "
        "SET applied_at = updated_at "
        "WHERE status = 'applied' AND applied_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("project_update_proposals", "applied_at")
