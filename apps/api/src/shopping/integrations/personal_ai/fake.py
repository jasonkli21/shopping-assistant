from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

from shopping.integrations.personal_ai.client import (
    AIProviderError,
    AIRequest,
    AIResponse,
    PersonalAIClient,
)


class FakePersonalAIClient(PersonalAIClient):
    """Task-aware deterministic adapter for offline intent development."""

    def __init__(
        self,
        *,
        scenario: str = "intent",
        delay_seconds: float = 0,
        response: dict[str, Any] | None = None,
        error_code: str | None = None,
        task_fixtures: dict[str, dict[str, dict[str, Any]]] | None = None,
    ) -> None:
        self.scenario = scenario
        self.delay_seconds = delay_seconds
        self.response = response
        self.error_code = error_code
        self.task_fixtures = task_fixtures or {}
        self.calls = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.calls += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error_code:
            raise AIProviderError(self.error_code)
        context = request.input.get("context", {})
        fixtures = self.task_fixtures.get(request.task, {})
        fixture_key = self._task_fixture_key(context)
        fixture = fixtures.get(fixture_key) or fixtures.get("*")
        if fixture is not None:
            return AIResponse(output=fixture)
        if request.task == "plan_product_research.v1":
            return AIResponse(output=self._plan_product_research(context))
        if request.task == "extract_claims.v1":
            return AIResponse(
                output={"claims": [], "explanation": "No claim fixture was supplied."}
            )
        if self.response is not None:
            return AIResponse(output=self.response)
        if request.task == "plan_discovery.v1":
            return AIResponse(output=self._plan_discovery(request.input.get("context", {})))
        if request.task not in {"interpret_shopping_intent.v1", "interpret_shopping_intent.v2"}:
            raise AIProviderError("unsupported_task")
        message = str(context.get("new_user_message", ""))
        result = self._interpret(
            message, context.get("requirements", []), context.get("current_state", {})
        )
        return result if isinstance(result, AIResponse) else AIResponse(output=result)

    def _interpret(
        self,
        message: str,
        requirements: list[dict[str, Any]],
        current_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | AIResponse:
        lowered = message.lower()
        current_state = current_state or {}
        products = current_state.get("products", [])
        if self.scenario == "malformed":
            return {
                "assistant_message": "Here is an incomplete proposal",
                "project_updates": {"budget_maximum": "400"},
            }
        if self.scenario == "refusal":
            return AIResponse(
                output={},
                refused=True,
            )
        if self.scenario == "foreign_id":
            return {
                "assistant_message": "I found a requirement to update.",
                "clarification_questions": [],
                "project_updates": {},
                "requirement_operations": [
                    {
                        "operation": "update",
                        "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
                        "fields": {"label": "Injected"},
                    }
                ],
            }
        if self.scenario == "invalid_budget":
            return {
                "assistant_message": "I understood the amount.",
                "clarification_questions": [],
                "project_updates": {
                    "budget_target": "500",
                    "budget_maximum": "400",
                    "budget_currency": "USD",
                },
                "requirement_operations": [],
            }

        if any(
            token in lowered
            for token in (
                "ignore previous",
                "reveal your instructions",
                "run a command",
                "fetch this url",
            )
        ):
            return {
                "assistant_message": "I can help refine the shopping goal.",
                "clarification_questions": ["What product are you shopping for?"],
                "project_updates": {},
                "requirement_operations": [],
            }

        if products and ("shortlist" in lowered or "short list" in lowered):
            return {
                "assistant_message": "I prepared a shortlist suggestion for your review.",
                "operations": [
                    {
                        "operation": "shortlist",
                        "project_product_id": products[0]["project_product_id"],
                        "reason": "Selected for further consideration.",
                    }
                ],
            }

        if products and "reject" in lowered:
            rejection_reason = next(
                (
                    reason
                    for phrase, reason in (
                        ("expensive", "too_expensive"),
                        ("too large", "too_large"),
                        ("missing feature", "missing_feature"),
                        ("weak evidence", "weak_evidence"),
                        ("wrong category", "wrong_category"),
                        ("appearance", "appearance"),
                    )
                    if phrase in lowered
                ),
                "other",
            )
            return {
                "assistant_message": (
                    "I prepared a rejection suggestion with a reason for your review."
                ),
                "operations": [
                    {
                        "operation": "reject",
                        "project_product_id": products[0]["project_product_id"],
                        "rejection_reason": rejection_reason,
                        "reason": message[:500],
                    }
                ],
            }

        if products and ("compare" in lowered or "differences" in lowered):
            selected = products[: min(3, len(products))]
            dimensions = []
            if "warranty" in lowered:
                dimensions.append(
                    {"key": "warranty", "label": "Warranty", "dimension_type": "evidence"}
                )
            if "price" in lowered or not dimensions:
                dimensions.append(
                    {"key": "price", "label": "Latest offer", "dimension_type": "offer"}
                )
            if "durability" in lowered:
                dimensions.append(
                    {
                        "key": "durability",
                        "label": "Durability evidence",
                        "dimension_type": "evidence",
                    }
                )
            return {
                "assistant_message": (
                    "I prepared a comparison using the selected products and requested dimensions."
                ),
                "operations": [
                    {
                        "operation": "set_comparison_dimensions",
                        "project_product_ids": [item["project_product_id"] for item in selected],
                        "dimensions": dimensions,
                        "display_mode": "differences"
                        if "difference" in lowered or "meaningful" in lowered
                        else "all",
                    }
                ],
            }

        if products and ("add a note" in lowered or "note that" in lowered):
            return {
                "assistant_message": "I prepared a product note for your review.",
                "operations": [
                    {
                        "operation": "add_note",
                        "project_product_id": products[0]["project_product_id"],
                        "text": message[:1000],
                    }
                ],
            }

        if "contradict" in lowered or ("quiet" in lowered and "loud" in lowered):
            return {
                "assistant_message": (
                    "I found requirements that may conflict, so I left the project unchanged."
                ),
                "clarification_questions": [
                    "Should quiet operation or maximum suction take priority?"
                ],
                "project_updates": {},
                "requirement_operations": [],
            }

        questions: list[str] = []
        updates: dict[str, Any] = {}
        operations: list[dict[str, Any]] = []
        assistant_message = (
            "I’ve noted the shopping details and prepared suggestions for your review."
        )

        if "vacuum" in lowered:
            updates["category"] = "Vacuum"
            if "hair" in lowered:
                operations.append(
                    {
                        "operation": "add",
                        "fields": {
                            "kind": "preference",
                            "label": "Works well with hair",
                            "detail": "The user asked for a vacuum that is good with hair.",
                        },
                    }
                )
            if "usd" in lowered:
                amount = _first_amount(message)
                if amount is not None:
                    updates["budget_maximum"] = amount
                    updates["budget_currency"] = "USD"
            elif "$" in message and _first_amount(message) is not None:
                amount = _first_amount(message)
                questions.append(f"Which currency should I use for the ${amount} budget?")
                assistant_message = "I can capture the budget after you confirm its currency."
            else:
                questions.append("What maximum budget and currency should I use?")

        elif "chair" in lowered and "desk" in lowered:
            measurement = _desk_measurement(message)
            if "under" in lowered and measurement is not None:
                dimension, unit, display_unit = measurement
                operations.append(
                    {
                        "operation": "add",
                        "fields": {
                            "kind": "constraint",
                            "label": (
                                f"Must fit under a desk with {dimension} {display_unit} clearance"
                            ),
                            "attribute_key": "height",
                            "operator": "lte",
                            "value": float(Decimal(dimension)),
                            "unit": unit,
                        },
                    }
                )
            elif any(character.isdigit() for character in message):
                questions.append(
                    "What is the desk clearance value and unit (inches or centimeters)?"
                )
            else:
                questions.append("What desk clearance should the chair fit under?")

        elif "monitor" in lowered and "alternatives" in lowered:
            questions.append(
                "What size, resolution, or main use should I prioritize for alternatives?"
            )
            assistant_message = (
                "I can compare alternatives once I know which monitor needs matter most."
            )
        elif "lightweight" in lowered:
            questions.append(
                "Do you mean easy to carry, low total weight, or a lightweight design?"
            )
            assistant_message = "I left “lightweight” open for clarification."
            operations = []
            updates = {}
        else:
            questions.append("What product and must-have details should I add to the project?")
            assistant_message = "Tell me a little more and I’ll prepare specific suggestions."

        # Existing IDs are never guessed by the fake; this branch only confirms
        # that the fixture context is being passed through as data.
        _ = [UUID(item["id"]) for item in requirements if "id" in item]
        return {
            "assistant_message": assistant_message,
            "clarification_questions": questions,
            "project_updates": updates,
            "requirement_operations": operations,
        }

    @staticmethod
    def _task_fixture_key(context: dict[str, Any]) -> str:
        source = context.get("source", {})
        if isinstance(source, dict) and isinstance(source.get("final_url"), str):
            return source["final_url"]
        target = context.get("target", {})
        if isinstance(target, dict) and isinstance(target.get("project_product_id"), str):
            return target["project_product_id"]
        return "*"

    @staticmethod
    def _plan_product_research(context: dict[str, Any]) -> dict[str, Any]:
        targets = context.get("selected_products", [])
        limit = context.get("limits", {}).get("maximum_queries", 8)
        queries: list[dict[str, str]] = []
        for target in targets:
            if not isinstance(target, dict) or len(queries) >= limit:
                continue
            target_id = target.get("project_product_id")
            name = " ".join(
                str(target.get(key) or "")
                for key in ("brand", "product_name", "model_family", "variant_name")
            ).strip()
            target_queries = (
                ("manufacturer_specification", f"{name} manufacturer specifications"),
                ("independent_measurement", f"{name} independent runtime test measured"),
                ("retailer_listing", f"{name} retailer listing"),
            )
            for source_class, text in target_queries:
                if len(queries) >= limit:
                    break
                queries.append(
                    {
                        "project_product_id": target_id,
                        "text": text[:300],
                        "purpose": f"Find {source_class.replace('_', ' ')} evidence.",
                        "source_class": source_class,
                    }
                )
        return {"queries": queries, "explanation": "Searches cover distinct source classes."}

    def _plan_discovery(self, context: dict[str, Any]) -> dict[str, Any]:
        """Produce task-shaped fixture plans without inventing product claims."""
        objective = str(context.get("objective", ""))
        project = context.get("project", {})
        requirements = context.get("requirements", [])
        combined = " ".join(
            [objective, str(project.get("goal", "")), str(project.get("category", ""))]
        ).casefold()
        if "monitor" in combined and not any(
            token in combined for token in ("inch", "resolution", "gaming", "office")
        ):
            return {
                "queries": [],
                "clarification": (
                    "What monitor size, resolution, or main use should guide discovery?"
                ),
                "explanation": "The request needs one more detail to create useful searches.",
            }
        if "impossible" in combined or ("quiet" in combined and "maximum suction" in combined):
            return {
                "queries": [],
                "clarification": "Which requirement should take priority for this search?",
                "explanation": "The current requirements may conflict.",
            }

        base_parts = [
            str(project.get("category") or "product"),
            objective or str(project.get("goal") or "shopping options"),
        ]
        max_budget = project.get("budget_maximum") or project.get("budget_target")
        currency = project.get("budget_currency")
        if max_budget and currency:
            base_parts.append(f"under {max_budget} {currency}")
        for requirement in requirements:
            if requirement.get("kind") in {"must_have", "constraint"}:
                base_parts.append(str(requirement.get("label", "")))
        text = " ".join(part for part in base_parts if part).strip()[:300]
        return {
            "queries": [
                {
                    "text": text,
                    "purpose": "Find products matching the project goal and required constraints.",
                }
            ],
            "clarification": None,
            "explanation": "The search phrase preserves the saved project requirements.",
        }


def _first_amount(message: str) -> str | None:
    import re

    match = re.search(r"\b(\d{1,6}(?:\.\d{1,2})?)\b", message)
    return match.group(1) if match else None


def _desk_measurement(message: str) -> tuple[str, str, str] | None:
    import re

    match = re.search(
        r"\b(\d{1,6}(?:\.\d{1,2})?)\s*-?\s*(inch(?:es)?|in|centimeters?|cm)\b",
        message,
        re.IGNORECASE,
    )
    if match is None:
        return None
    amount, supplied_unit = match.groups()
    if supplied_unit.lower().startswith("in"):
        return amount, "in", "in"
    return amount, "cm", "cm"
