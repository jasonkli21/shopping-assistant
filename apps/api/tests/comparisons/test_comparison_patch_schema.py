import pytest
from pydantic import ValidationError

from shopping.comparisons.schemas import ComparisonPatch


@pytest.mark.parametrize(
    "field",
    ["title", "project_product_ids", "dimensions", "display_mode"],
)
def test_comparison_patch_rejects_null_for_non_nullable_changes(field):
    with pytest.raises(ValidationError, match="comparison fields cannot be cleared with null"):
        ComparisonPatch.model_validate(
            {
                "expected_version": 1,
                "expected_comparison_version": 1,
                field: None,
            }
        )


def test_comparison_patch_accepts_a_typed_dimensions_change():
    patch = ComparisonPatch.model_validate(
        {
            "expected_version": 1,
            "expected_comparison_version": 1,
            "dimensions": [
                {
                    "key": "warranty",
                    "label": "Warranty",
                    "dimension_type": "evidence",
                }
            ],
        }
    )

    assert patch.dimensions[0].key == "warranty"
