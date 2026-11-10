"""実SDKを模擬HTTP通信へ接続する共通fixture。"""

from collections.abc import Callable, Iterator

import anthropic
import httpx2
import pytest


@pytest.fixture
def mock_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[Callable[[httpx2.Request], httpx2.Response]], None]]:
    sdk_class = anthropic.Anthropic
    clients: list[anthropic.Anthropic] = []

    def install(handler: Callable[[httpx2.Request], httpx2.Response]) -> None:
        def create(*, timeout: float, max_retries: int) -> anthropic.Anthropic:
            client = sdk_class(
                api_key="test-key",
                base_url="https://llm.test",
                http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
                timeout=timeout,
                max_retries=max_retries,
            )
            clients.append(client)
            return client

        monkeypatch.setattr(anthropic, "Anthropic", create)

    yield install
    for client in clients:
        assert client.is_closed()
