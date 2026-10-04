from shopping.config import Settings
from shopping.search.fake import FakeSearchProvider
from shopping.search.provider import SearchProvider
from shopping.search.tavily import TavilySearchProvider


def create_search_provider(settings: Settings) -> SearchProvider:
    """Select exactly the configured provider; a failed live adapter never falls back."""
    if settings.search_provider == "fake":
        return FakeSearchProvider()
    if settings.search_provider == "tavily":
        return TavilySearchProvider(settings.tavily_api_key)
    raise ValueError(f"Unknown SEARCH_PROVIDER: {settings.search_provider}")
