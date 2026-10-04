from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AIRequest:
    task: str
    input: dict[str, Any]


@dataclass(frozen=True)
class AIResponse:
    output: dict[str, Any]


class PersonalAIClient(Protocol):
    """Boundary to the separate personal-ai-system.

    Shopping-domain code should depend on this protocol rather than a concrete
    model SDK or the internal implementation of the personal-ai-system.
    """

    async def generate(self, request: AIRequest) -> AIResponse: ...
