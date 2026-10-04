from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AIRequest:
    task: str
    input: dict[str, Any]


@dataclass(frozen=True)
class AIResponse:
    output: dict[str, Any]
    provider_request_id: str | None = None
    refused: bool = False


class AIProviderError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PersonalAIClient(Protocol):
    """Boundary to the separate personal-ai-system.

    Shopping-domain code should depend on this protocol rather than a concrete
    model SDK or the internal implementation of the personal-ai-system.
    """

    async def generate(self, request: AIRequest) -> AIResponse: ...


class UnavailablePersonalAIClient(PersonalAIClient):
    """Explicitly disabled until a verified task endpoint/schema is available."""

    async def generate(self, request: AIRequest) -> AIResponse:
        raise AIProviderError("provider_unavailable")
