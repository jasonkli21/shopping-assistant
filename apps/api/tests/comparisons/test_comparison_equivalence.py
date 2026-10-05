from shopping.comparisons.service import _demonstrably_equal, _normalize


def test_equivalent_measurements_normalize_to_the_same_unit():
    centimetres = _normalize(2.54, "cm", "width")
    millimetres = _normalize(25.4, "mm", "width")

    assert centimetres == millimetres == ("25.4", "mm", True)


def test_unconverted_units_are_part_of_dimension_equality():
    cells = [
        {"status": "known", "comparison_value": {"value": "12", "unit": "L"}},
        {"status": "known", "comparison_value": {"value": "12", "unit": "gal"}},
    ]

    assert _demonstrably_equal(cells) is False


def test_unknown_values_are_never_considered_equal():
    cells = [
        {"status": "unknown", "comparison_value": None},
        {"status": "unknown", "comparison_value": None},
    ]

    assert _demonstrably_equal(cells) is False
