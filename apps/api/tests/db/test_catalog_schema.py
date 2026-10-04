from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
from shopping.projects.models import ShoppingProject

pytestmark = pytest.mark.db


def test_catalog_relations_and_timestamped_offers_allow_currency_history(db_engine):
    owner_id = uuid4()
    project_id, product_id, variant_id = uuid4(), uuid4(), uuid4()
    project = ShoppingProject(
        id=project_id,
        owner_id=owner_id,
        title="Monitor",
        goal="Find a 27 inch monitor",
        revision=1,
    )
    product = Product(
        id=product_id,
        owner_id=owner_id,
        canonical_name="Example Monitor",
        brand="Example",
        brand_key="example",
        category="monitor",
    )
    variant = ProductVariant(
        id=variant_id,
        product_id=product_id,
        display_name="27 inch, US model",
        identity_key="region:us|size:27-inch",
        identity_attributes={"region": {"value": "US", "origin": "source"}},
        category_attributes={"screen_size": {"value": 27, "unit": "inch", "origin": "source"}},
    )
    first_seen = datetime.now(UTC)
    project_product = ProjectProduct(
        project_id=project_id,
        variant_id=variant_id,
        discovery_reason="Found in a search result",
    )
    with Session(db_engine) as session:
        session.add_all([project, product])
        session.flush()
        session.add(variant)
        session.flush()
        session.add_all(
            [
                project_product,
                RetailOffer(
                    owner_id=owner_id,
                    variant_id=variant_id,
                    idempotency_key="observation-usd",
                    retailer_name="Example Store",
                    retailer_domain="store.example",
                    url="https://store.example/monitor?sku=us",
                    amount=Decimal("299.99"),
                    currency="USD",
                    availability="in_stock",
                    condition="new",
                    observed_at=first_seen,
                ),
                RetailOffer(
                    owner_id=owner_id,
                    variant_id=variant_id,
                    idempotency_key="observation-cad",
                    retailer_name="Example Store CA",
                    retailer_domain="store.example",
                    url="https://store.example/monitor?sku=us",
                    amount=Decimal("409.99"),
                    currency="CAD",
                    availability="unknown",
                    condition="new",
                    observed_at=first_seen + timedelta(minutes=1),
                ),
                RetailOffer(
                    owner_id=owner_id,
                    variant_id=variant_id,
                    idempotency_key="observation-unknown-price",
                    retailer_name="Example Marketplace",
                    url="https://market.example/monitor",
                    amount=None,
                    currency=None,
                    availability="unknown",
                    condition="unknown",
                    observed_at=first_seen + timedelta(minutes=2),
                ),
            ]
        )
        session.commit()

        offers = list(
            session.scalars(
                select(RetailOffer)
                .where(RetailOffer.variant_id == variant_id)
                .order_by(RetailOffer.observed_at)
            )
        )
        assert [offer.currency for offer in offers] == ["USD", "CAD", None]
        assert [offer.amount for offer in offers] == [Decimal("299.99"), Decimal("409.99"), None]
        assert (
            session.scalar(select(ProjectProduct.id).where(ProjectProduct.project_id == project_id))
            == project_product.id
        )


def test_catalog_database_rejects_offer_with_negative_price(db_engine):
    owner_id = uuid4()
    product_id, variant_id = uuid4(), uuid4()
    product = Product(id=product_id, owner_id=owner_id, canonical_name="Example Vacuum")
    variant = ProductVariant(
        id=variant_id,
        product_id=product_id,
        display_name="Unspecified",
        identity_key="unspecified",
    )
    with Session(db_engine) as session:
        session.add(product)
        session.flush()
        session.add(variant)
        session.flush()
        session.add(
            RetailOffer(
                owner_id=owner_id,
                variant_id=variant_id,
                idempotency_key="invalid-negative",
                retailer_name="Example Store",
                url="https://store.example/vacuum",
                amount=Decimal("-1.00"),
                currency="USD",
                availability="unknown",
                condition="unknown",
                observed_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
