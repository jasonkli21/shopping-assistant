import pytest
from sqlalchemy import CheckConstraint, text

from shopping.preferences.models import PreferenceCandidate, ShoppingPreference, ShoppingProfile
from shopping.projects.models import ProjectRequirement, ShoppingProject

pytestmark = pytest.mark.db


def test_phase8_tables_and_project_provenance_exist_after_migration(db_engine):
    with db_engine.connect() as connection:
        columns = connection.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name IN "
                "('shopping_profiles', 'shopping_preferences', 'preference_candidates', "
                "'shopping_projects', 'project_requirements')"
            )
        ).all()
    by_table = {}
    for table, column in columns:
        by_table.setdefault(table, set()).add(column)
    assert {"id", "owner_id", "revision", "reuse_enabled"} <= by_table["shopping_profiles"]
    assert {
        "profile_id",
        "source_candidate_id",
        "source_project_id",
        "source_requirement_id",
        "source_kind",
        "source_project_product_id",
        "source_decision_id",
        "category_scopes",
        "status",
        "revision",
    } <= by_table["shopping_preferences"]
    assert {
        "source_project_revision",
        "proposition_hash",
        "status",
        "source_kind",
        "source_project_product_id",
        "source_decision_id",
    } <= by_table["preference_candidates"]
    assert "reuse_preferences" in by_table["shopping_projects"]
    assert {
        "source_preference_id",
        "source_preference_revision",
        "source_preference_scope",
    } <= by_table["project_requirements"]


def test_phase8_constraints_keep_profile_state_bounded_and_soft():
    def checks(model):
        return {
            item.name for item in model.__table__.constraints if isinstance(item, CheckConstraint)
        }

    assert "ck_shopping_profile_revision" in checks(ShoppingProfile)
    assert {"ck_preference_strength", "ck_preference_status", "ck_preference_value_size"} <= checks(
        ShoppingPreference
    )
    assert {
        "ck_candidate_status",
        "ck_candidate_hash",
        "ck_candidate_scopes_size",
        "ck_candidate_source_kind",
    } <= checks(PreferenceCandidate)
    assert ProjectRequirement.__table__.c.source_preference_id is not None
    assert ShoppingProject.__table__.c.reuse_preferences is not None
