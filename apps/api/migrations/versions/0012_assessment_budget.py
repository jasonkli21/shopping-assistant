"""Allow the full accepted requirement snapshot to be assessed."""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_assessment_budget"
down_revision: str | None = "0011_source_stage_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_assessment_requirements_size", "product_assessments", type_="check")
    op.create_check_constraint(
        "ck_assessment_requirements_size",
        "product_assessments",
        "octet_length(requirements_snapshot::text) <= 1500000",
    )
    op.drop_constraint("ck_assessment_conclusions_size", "product_assessments", type_="check")
    op.create_check_constraint(
        "ck_assessment_conclusions_size",
        "product_assessments",
        "octet_length(conclusions::text) <= 1500000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_assessment_requirements_size", "product_assessments", type_="check")
    op.create_check_constraint(
        "ck_assessment_requirements_size",
        "product_assessments",
        "octet_length(requirements_snapshot::text) <= 24000",
    )
    op.drop_constraint("ck_assessment_conclusions_size", "product_assessments", type_="check")
    op.create_check_constraint(
        "ck_assessment_conclusions_size",
        "product_assessments",
        "octet_length(conclusions::text) <= 12000",
    )
