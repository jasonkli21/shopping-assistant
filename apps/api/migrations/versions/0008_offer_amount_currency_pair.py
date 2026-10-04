"""Require offers to store amount and currency as a complete pair."""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_offer_amount_currency_pair"
down_revision: str | None = "0007_catalog_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_offer_amount_currency", "retail_offers", type_="check")
    op.create_check_constraint(
        "ck_offer_amount_currency",
        "retail_offers",
        "(amount IS NULL AND currency IS NULL) OR "
        "(amount IS NOT NULL AND currency IS NOT NULL AND amount >= 0 "
        "AND currency ~ '^[A-Z]{3}$')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_offer_amount_currency", "retail_offers", type_="check")
    op.create_check_constraint(
        "ck_offer_amount_currency",
        "retail_offers",
        "(amount IS NULL AND currency IS NULL) OR (amount >= 0 AND currency ~ '^[A-Z]{3}$')",
    )
