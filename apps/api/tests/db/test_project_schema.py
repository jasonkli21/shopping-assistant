from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.projects.models import ProjectRequirement, ShoppingProject

pytestmark = pytest.mark.db


def test_project_and_jsonb_requirement_round_trip(db_engine):
    project_id = uuid4()
    owner_id = uuid4()
    requirement_id = uuid4()
    with Session(db_engine) as session:
        project = ShoppingProject(
            id=project_id,
            owner_id=owner_id,
            title="Vacuum for apartment",
            goal="Find a vacuum that works well for pet hair.",
            budget_maximum=Decimal("400.00"),
            budget_currency="USD",
            revision=1,
        )
        project.requirements.append(
            ProjectRequirement(
                id=requirement_id,
                kind="must_have",
                label="Works well on pet hair",
                attribute_key="pet_hair_pickup",
                operator="eq",
                value={"level": "strong", "verified": True},
                unit=None,
                position=0,
                origin="user",
            )
        )
        session.add(project)
        session.commit()

        stored = session.scalar(select(ShoppingProject).where(ShoppingProject.id == project_id))
        assert stored is not None
        assert stored.budget_maximum == Decimal("400.00")
        assert stored.budget_currency == "USD"
        assert stored.created_at.tzinfo is not None
        assert stored.updated_at.tzinfo is not None
        requirement = session.scalar(
            select(ProjectRequirement).where(ProjectRequirement.id == requirement_id)
        )
        assert requirement is not None
        assert requirement.value == {"level": "strong", "verified": True}


@pytest.mark.parametrize(
    ("target", "maximum", "currency"),
    [
        (Decimal("401"), Decimal("400"), "USD"),
        (Decimal("-1"), Decimal("400"), "USD"),
        (Decimal("100"), None, None),
    ],
)
def test_database_rejects_invalid_budget_combinations(db_engine, target, maximum, currency):
    with Session(db_engine) as session:
        session.add(
            ShoppingProject(
                owner_id=uuid4(),
                title="Vacuum",
                goal="Find a vacuum",
                budget_target=target,
                budget_maximum=maximum,
                budget_currency=currency,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_foreign_keys_and_transaction_rollback_are_enforced(db_engine):
    with Session(db_engine) as session:
        session.add(
            ProjectRequirement(
                project_id=uuid4(),
                kind="must_have",
                label="Pet hair",
                position=0,
                origin="user",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(select(ShoppingProject.id)) is None


def test_schema_uses_postgresql_specific_jsonb_and_uuid(db_engine):
    with db_engine.connect() as connection:
        column_rows = connection.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'project_requirements'"
            )
        ).all()
    types = {name: data_type for name, data_type in column_rows}
    assert types["value"] == "jsonb"
    assert types["id"] == "uuid"
