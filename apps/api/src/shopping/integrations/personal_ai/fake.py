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
    ) -> None:
        self.scenario = scenario
        self.delay_seconds = delay_seconds
        self.response = response
        self.error_code = error_code
        self.calls = 0

    async def generate(self, request: AIRequest) -> AIResponse:
        self.calls += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error_code:
            raise AIProviderError(self.error_code)
        if self.response is not None:
            return AIResponse(output=self.response)
        if request.task != "interpret_shopping_intent.v1":
            raise AIProviderError("unsupported_task")
        context = request.input.get("context", {})
        message = str(context.get("new_user_message", ""))
        result = self._interpret(message, context.get("requirements", []))
        return result if isinstance(result, AIResponse) else AIResponse(output=result)

    def _interpret(
        self, message: str, requirements: list[dict[str, Any]]
    ) -> dict[str, Any] | AIResponse:
        lowered = message.lower()
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
                questions.append("Which currency should I use for the $400 budget?")
                assistant_message = "I can capture the budget after you confirm its currency."
            else:
                questions.append("What maximum budget and currency should I use?")

        elif "chair" in lowered and "desk" in lowered:
            if "under" in lowered and any(character.isdigit() for character in message):
                dimension = _first_amount(message)
                if dimension is not None:
                    operations.append(
                        {
                            "operation": "add",
                            "fields": {
                                "kind": "constraint",
                                "label": f"Must fit under a {dimension} inch desk",
                                "attribute_key": "height",
                                "operator": "lte",
                                "value": float(Decimal(dimension)),
                                "unit": "in",
                            },
                        }
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


def _first_amount(message: str) -> str | None:
    import re

    match = re.search(r"\b(\d{1,6}(?:\.\d{1,2})?)\b", message)
    return match.group(1) if match else None
