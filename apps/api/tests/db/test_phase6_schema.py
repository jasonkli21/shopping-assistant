import pytest
from sqlalchemy import CheckConstraint, text

from shopping.catalog.models import SavedProduct
from shopping.comparisons.models import (
    ComparisonDimension,
    ComparisonItem,
    ComparisonSnapshot,
    SavedComparison,
)
from shopping.projects.models import DecisionEvent, ProjectProductDecision, UserNote

pytestmark = pytest.mark.db


def test_phase6_tables_and_snapshot_jsonb_exist_after_migration(db_engine):
    with db_engine.connect() as connection:
        columns = connection.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name IN "
                "('project_product_decisions', 'decision_events', 'user_notes', 'saved_products', "
                "'comparisons', 'comparison_items', 'comparison_dimensions', "
                "'comparison_snapshots')"
            )
        ).all()
    by_table = {}
    for table, column, data_type in columns:
        by_table.setdefault(table, {})[column] = data_type
    assert set(by_table) == {
        "project_product_decisions",
        "decision_events",
        "user_notes",
        "saved_products",
        "comparisons",
        "comparison_items",
        "comparison_dimensions",
        "comparison_snapshots",
    }
    assert by_table["comparison_snapshots"]["view"] == "jsonb"
    assert by_table["project_product_decisions"]["state"] == "character varying"
    assert by_table["saved_products"]["version"] == "integer"


def test_phase6_model_constraints_encode_mutually_exclusive_and_bounded_state():
    def checks(model):
        return {
            item.name for item in model.__table__.constraints if isinstance(item, CheckConstraint)
        }

    assert "ck_decision_rejection_state" in checks(ProjectProductDecision)
    assert {
        "ck_decision_event_from_state",
        "ck_decision_event_to_state",
        "ck_decision_event_actor",
        "ck_decision_event_request_key",
        "ck_decision_event_concerns_size",
    } <= checks(DecisionEvent)
    assert "ck_comparison_snapshot_size" in checks(ComparisonSnapshot)
    assert "ck_comparison_item_position" in checks(ComparisonItem)
    assert "ck_comparison_dimension_type" in checks(ComparisonDimension)
    assert "ck_comparison_revision" in checks(SavedComparison)
    assert "ck_user_note_text" in checks(UserNote)
    assert "ck_saved_product_version" in checks(SavedProduct)
