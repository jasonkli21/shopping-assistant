from types import SimpleNamespace
from uuid import uuid4

from shopping.evidence.reads import assessment_context_stale


def _requirement(label="Works well on pet hair"):
    return SimpleNamespace(
        id=uuid4(),
        position=0,
        kind="must_have",
        label=label,
        detail=None,
        attribute_key=None,
        operator=None,
        value=None,
        unit=None,
    )


def _snapshot(requirement):
    return [
        {
            "id": str(requirement.id),
            "kind": requirement.kind,
            "label": requirement.label,
            "detail": requirement.detail,
            "attribute_key": requirement.attribute_key,
            "operator": requirement.operator,
            "value": requirement.value,
            "unit": requirement.unit,
        }
    ]


def test_notes_or_other_project_revision_changes_do_not_make_fit_stale():
    requirement = _requirement()
    assessment = SimpleNamespace(
        requirements_snapshot=_snapshot(requirement), product_revision=3, variant_revision=2
    )
    project = SimpleNamespace(requirements=[requirement], revision=8)
    product = SimpleNamespace(revision=3)
    variant = SimpleNamespace(revision=2)

    assert assessment_context_stale(assessment, project, product, variant) is False


def test_requirement_product_or_variant_changes_make_fit_stale():
    original = _requirement()
    assessment = SimpleNamespace(
        requirements_snapshot=_snapshot(original), product_revision=3, variant_revision=2
    )
    project = SimpleNamespace(requirements=[_requirement()], revision=2)
    same_requirements = SimpleNamespace(requirements=[original])

    assert (
        assessment_context_stale(
            assessment, project, SimpleNamespace(revision=3), SimpleNamespace(revision=2)
        )
        is True
    )
    assert (
        assessment_context_stale(
            assessment,
            same_requirements,
            SimpleNamespace(revision=4),
            SimpleNamespace(revision=2),
        )
        is True
    )
    assert (
        assessment_context_stale(
            assessment,
            same_requirements,
            SimpleNamespace(revision=3),
            SimpleNamespace(revision=3),
        )
        is True
    )
