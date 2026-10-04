"""Bound project revision and notes at the database boundary."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_project_revision_notes"
down_revision: str | None = "0001_projects_requirements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint("ck_project_revision_positive", "shopping_projects", "revision >= 1")
    op.create_check_constraint(
        "ck_project_notes_length",
        "shopping_projects",
        "notes IS NULL OR char_length(notes) <= 10000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_project_notes_length", "shopping_projects", type_="check")
    op.drop_constraint("ck_project_revision_positive", "shopping_projects", type_="check")
