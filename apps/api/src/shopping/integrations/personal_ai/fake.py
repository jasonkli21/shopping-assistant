from shopping.integrations.personal_ai.client import AIRequest, AIResponse, PersonalAIClient


class FakePersonalAIClient(PersonalAIClient):
    """Deterministic no-op AI adapter for foundation tests and offline development."""

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(output={"task": request.task, "input": request.input})
