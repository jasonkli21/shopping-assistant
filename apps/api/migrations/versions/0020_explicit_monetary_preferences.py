"""Declare monetary preference intent explicitly."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p9_monetary_preferences"
down_revision: str | None = "p9_shopping_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("preference_candidates", "shopping_preferences"):
        op.add_column(
            table,
            sa.Column("monetary", sa.Boolean(), server_default=sa.false(), nullable=False),
        )
        op.execute(
            sa.text(
                f"UPDATE {table} SET monetary = true "
                "WHERE lower(key || ' ' || label) ~ '(budget|price|cost|spend|currency|amount)'"
            )
        )


def downgrade() -> None:
    op.drop_column("shopping_preferences", "monetary")
    op.drop_column("preference_candidates", "monetary")
