"""Offline transport for composition tests of the shared provider boundary."""

from api.openrouter import CreditsResult, CreditsStatus
from tests.test_message_sending import (
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
)


class FakeProviderRouter(FakeKeyValidator):
    async def get_credits(self, _api_key: str) -> CreditsResult:
        return CreditsResult(CreditsStatus.RESTRICTED)

    async def fetch_models(self, api_key: str):
        return await FakeCatalogClient(()).fetch_models(api_key)

    async def complete(self, *args, **kwargs):
        return await FakeCompletionClient([]).complete(*args, **kwargs)

    async def aclose(self) -> None:
        pass
