"""Deterministic compaction for model-facing project requirement context."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any


def compact_requirement_descriptions(
    context: dict[str, Any],
    *,
    max_chars: int,
    measure: Callable[[dict[str, Any]], int] | None = None,
) -> dict[str, Any]:
    """Fit requirements by trimming descriptions while preserving structured data.

    Only requirement ``label`` and ``detail`` text is compacted. IDs, kinds, structured
    criteria, units, provenance, and every other context field are copied unchanged. The
    optional measurement callback can include the enclosing AI request envelope in the budget.
    """

    if max_chars <= 0:
        raise ValueError("context size limit must be positive")
    measure_size = measure or _json_size
    original = copy.deepcopy(context)
    requirements = original.get("requirements", [])
    if not isinstance(requirements, list) or any(
        not isinstance(item, dict) for item in requirements
    ):
        raise ValueError("project requirements must be a list of objects")

    labels = [
        item.get("label") if isinstance(item.get("label"), str) else "" for item in requirements
    ]
    details = [item.get("detail") for item in requirements]
    full_label_lengths = [len(label) for label in labels]
    full_detail_lengths = [len(detail) if isinstance(detail, str) else 0 for detail in details]

    def build(label_lengths: list[int], detail_lengths: list[int] | None) -> dict[str, Any]:
        result = copy.deepcopy(original)
        compacted = copy.deepcopy(requirements)
        for index, item in enumerate(compacted):
            item["label"] = _fit_text(labels[index], label_lengths[index])
            detail = details[index]
            if isinstance(detail, str):
                item["detail"] = (
                    None
                    if detail_lengths is None or detail_lengths[index] == 0
                    else _fit_text(detail, detail_lengths[index])
                )
        result["requirements"] = compacted
        return result

    full = build(full_label_lengths, full_detail_lengths)
    if measure_size(full) <= max_chars:
        return full

    labels_only = build(full_label_lengths, None)
    if measure_size(labels_only) <= max_chars:
        detail_lengths = _allocate_text(
            details,
            [0] * len(details),
            max_chars=max_chars,
            measure=measure_size,
            build=lambda lengths: build(full_label_lengths, lengths),
        )
        return build(full_label_lengths, detail_lengths)

    minimum_label_lengths = [min(1, len(label)) for label in labels]
    minimum_labels = build(minimum_label_lengths, None)
    if measure_size(minimum_labels) > max_chars:
        raise ValueError("project context exceeds its configured size limit after compaction")

    label_lengths = _allocate_text(
        labels,
        minimum_label_lengths,
        max_chars=max_chars,
        measure=measure_size,
        build=lambda lengths: build(lengths, None),
    )
    detail_lengths = _allocate_text(
        details,
        [0] * len(details),
        max_chars=max_chars,
        measure=measure_size,
        build=lambda lengths: build(label_lengths, lengths),
    )
    return build(label_lengths, detail_lengths)


def _allocate_text(
    values: list[Any],
    initial_lengths: list[int],
    *,
    max_chars: int,
    measure: Callable[[dict[str, Any]], int],
    build: Callable[[list[int]], dict[str, Any]],
) -> list[int]:
    texts = [value if isinstance(value, str) else "" for value in values]
    upper = max((len(value) for value in texts), default=0)
    low = min(initial_lengths, default=0)
    high = upper
    while low < high:
        middle = (low + high + 1) // 2
        candidate_lengths = [
            max(initial_lengths[index], min(middle, len(text))) for index, text in enumerate(texts)
        ]
        if measure(build(candidate_lengths)) <= max_chars:
            low = middle
        else:
            high = middle - 1

    allocated = [
        max(initial_lengths[index], min(low, len(text))) for index, text in enumerate(texts)
    ]
    while True:
        advanced = False
        for index, text in enumerate(texts):
            if allocated[index] >= len(text):
                continue
            candidate_lengths = list(allocated)
            candidate_lengths[index] += 1
            if measure(build(candidate_lengths)) <= max_chars:
                allocated[index] += 1
                advanced = True
        if not advanced:
            break
    return allocated


def _fit_text(value: str, length: int) -> str:
    if length >= len(value):
        return value
    return f"{value[:length]}…"


def _json_size(value: dict[str, Any]) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("project context must be bounded JSON") from error
