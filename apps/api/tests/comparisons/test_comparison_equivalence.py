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


def test_distinct_unparsed_evidence_assertions_remain_visible():
    cells = [
        {
            "status": "known",
            "comparison_value": {
                "value": None,
                "assertion": "lasts about a year",
                "evidence_category": "manufacturer_claim",
                "qualifiers": {"condition": "normal use"},
            },
        },
        {
            "status": "known",
            "comparison_value": {
                "value": None,
                "assertion": "customers report early wear",
                "evidence_category": "individual_anecdote",
                "qualifiers": {"condition": "normal use"},
            },
        },
    ]

    assert _demonstrably_equal(cells) is False


def test_mixed_assessments_are_not_hidden_as_equal_known_values():
    cells = [
        {"status": "conflict", "comparison_value": None},
        {"status": "conflict", "comparison_value": None},
    ]

    assert _demonstrably_equal(cells) is False
