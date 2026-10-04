import asyncio

import pytest

from shopping.integrations.personal_ai.client import (
    AIProviderError,
    AIRequest,
    UnavailablePersonalAIClient,
)


def test_unavailable_external_adapter_fails_closed_without_network_calls():
    request = AIRequest(task="interpret_shopping_intent.v1", input={})
    client = UnavailablePersonalAIClient()

    with pytest.raises(AIProviderError) as error:
        asyncio.run(client.generate(request))

    assert error.value.code == "provider_unavailable"
