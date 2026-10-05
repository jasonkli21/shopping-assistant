from shopping.evidence.classification import classify_claim, classify_source


def test_spoofed_publisher_hosts_remain_unknown():
    for url in (
        "https://rtings.com.evil.example/review",
        "https://myrtings.com/review",
        "https://amazon.com.evil.example/listing",
        "https://official-vacuum.example/specs",
    ):
        assert (
            classify_source(url, text="We measured runtime in a test.").classification == "unknown"
        )


def test_claim_origin_can_be_weaker_than_publisher():
    assert (
        classify_claim(
            "independent_measurement",
            "According to the manufacturer, runtime is 60 minutes.",
            "AX-4 HEPA",
        )
        == "manufacturer_claim"
    )
    assert (
        classify_claim(
            "independent_measurement", "In my experience it lasts 20 minutes.", "AX-4 HEPA"
        )
        == "individual_anecdote"
    )
    assert (
        classify_claim("independent_measurement", "Runtime is 40 minutes.", "AX-4 HEPA")
        == "editorial_assessment"
    )
    assert (
        classify_claim(
            "independent_measurement", "Up to 60 minutes runtime.", "AX-4 HEPA runtime test"
        )
        == "manufacturer_claim"
    )


def test_recognized_review_host_needs_measurement_content_for_measurement_class():
    assert (
        classify_source(
            "https://www.rtings.com/vacuum/reviews/ax-4",
            title="AX-4 Review",
            text="The AX-4 is a compelling vacuum with premium features.",
        ).classification
        == "editorial_assessment"
    )
    assert (
        classify_source(
            "https://www.rtings.com/vacuum/reviews/ax-4",
            title="AX-4 Runtime Test",
            text="We measured 37 minutes runtime in normal mode.",
        ).classification
        == "independent_measurement"
    )
    assert (
        classify_source(
            "https://www.rtings.com/vacuum/reviews/ax-4",
            text="We tested the model. The manufacturer says it runs for up to 60 minutes.",
        ).classification
        == "editorial_assessment"
    )
