"""実際のAnthropic SDKと模擬HTTP通信でAPIの境界を検証する。"""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx2
import pytest
from anthropic import Anthropic

from coding_agent.anthropic_client import (
    DEFAULT_MODEL,
    SONNET_MODEL,
    AnthropicClient,
    AnthropicConfig,
)
from coding_agent.llm import (
    LLMAuthenticationError,
    LLMClient,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMRequestError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
    LLMTruncatedResponseError,
    Message,
    TokenUsage,
)


def response_body(model: str = DEFAULT_MODEL) -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": "こんにちは！"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 30,
            "cache_creation_input_tokens": 5,
            "cache_read_input_tokens": 7,
            "output_tokens_details": {"thinking_tokens": 20},
        },
    }


@contextmanager
def mock_client(
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    config: AnthropicConfig | None = None,
) -> Iterator[AnthropicClient]:
    with (
        httpx2.Client(transport=httpx2.MockTransport(handler)) as http,
        Anthropic(
            api_key="test-key", base_url="https://llm.test", http_client=http
        ) as sdk,
    ):
        yield AnthropicClient(sdk, config=config)


@pytest.mark.parametrize("model", [DEFAULT_MODEL, SONNET_MODEL])
def test_model_selection_and_history_conversion(model: str) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 30.0
        )
        assert request.headers["anthropic-version"] == "2026-10-21"
        return httpx2.Response(200, json=response_body(model))

    messages = [
        Message("system", "Be helpful."),
        Message("user", "Hi"),
        Message("assistant", "Hello"),
        Message("system", "Answer in Japanese."),
        Message("user", "挨拶して"),
    ]
    with mock_client(handler, config=AnthropicConfig(model=model)) as adapter:
        client: LLMClient = adapter
        result = client.complete(messages)

    assert result == LLMResponse("こんにちは！", model, TokenUsage(10, 30, 5, 7, 20))
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/messages"
    assert json.loads(requests[0].content) == {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": 16_000,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium"},
        "stream": False,
    }


def test_default_model_is_haiku() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert json.loads(request.content)["model"] == DEFAULT_MODEL
        return httpx2.Response(200, json=response_body())

    with mock_client(handler) as client:
        assert client.complete([Message("user", "Hi")]).model == DEFAULT_MODEL


def test_output_budget_effort_and_timeout_can_be_configured() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert body["max_tokens"] == 8192
        assert body["output_config"] == {"effort": "high"}
        assert request.extensions["timeout"]["read"] == 120.0
        return httpx2.Response(200, json=response_body())

    config = AnthropicConfig(
        max_output_tokens=8192, effort="high", timeout_seconds=120.0
    )
    with mock_client(handler, config=config) as client:
        client.complete([Message("user", "Hi")])


def test_thinking_is_not_exposed_and_text_blocks_keep_their_order() -> None:
    body = response_body()
    body["content"] = [
        {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
        {"type": "text", "text": "前半\n"},
        {"type": "redacted_thinking", "data": "private redacted data"},
        {"type": "text", "text": "後半"},
    ]
    with mock_client(lambda _: httpx2.Response(200, json=body)) as client:
        assert client.complete([Message("user", "Hi")]).text == "前半\n後半"


@pytest.mark.parametrize("missing_usage", [False, True])
def test_unavailable_usage_is_unknown(missing_usage: bool) -> None:
    body = response_body()
    if missing_usage:
        del body["usage"]
    else:
        body["usage"] = None
    with mock_client(lambda _: httpx2.Response(200, json=body)) as client:
        assert client.complete([Message("user", "Hi")]).usage is None


def test_optional_usage_details_are_unknown_or_zero() -> None:
    body = response_body()
    body["usage"] = {"input_tokens": 10, "output_tokens": 30}
    with mock_client(lambda _: httpx2.Response(200, json=body)) as client:
        assert client.complete([Message("user", "Hi")]).usage == TokenUsage(10, 30)


@pytest.mark.parametrize("reason", ["max_tokens", "model_context_window_exceeded"])
def test_truncation_keeps_usage_without_retry(reason: str) -> None:
    attempts = 0
    body = response_body()
    body["stop_reason"] = reason

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(200, json=body)

    with mock_client(handler) as client:
        with pytest.raises(LLMTruncatedResponseError) as error:
            client.complete([Message("user", "Hi")])

    assert error.value.model == DEFAULT_MODEL
    assert error.value.stop_reason == reason
    assert error.value.usage == TokenUsage(10, 30, 5, 7, 20)
    assert "こんにちは" not in str(error.value)
    assert attempts == 1


def test_refusal_does_not_fall_back_or_retry() -> None:
    requests: list[httpx2.Request] = []
    body = response_body()
    body["stop_reason"] = "refusal"

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=body)

    with mock_client(handler) as client:
        with pytest.raises(LLMRefusalError) as error:
            client.complete([Message("user", "Hi")])
    assert len(requests) == 1
    assert error.value.stop_reason == "refusal"
    assert error.value.usage == TokenUsage(10, 30, 5, 7, 20)


@pytest.mark.parametrize("reason", ["tool_use", "pause_turn", "stop_sequence", None])
def test_unsupported_endings_are_not_returned_as_success(reason: str | None) -> None:
    body = response_body()
    body["stop_reason"] = reason
    with mock_client(lambda _: httpx2.Response(200, json=body)) as client:
        with pytest.raises(LLMResponseError, match="did not finish normally"):
            client.complete([Message("user", "Hi")])


@pytest.mark.parametrize("text", ["", " \n "])
def test_empty_text_is_an_error(text: str) -> None:
    body = response_body()
    body["content"] = [{"type": "text", "text": text}]
    with mock_client(lambda _: httpx2.Response(200, json=body)) as client:
        with pytest.raises(LLMResponseError, match="no text"):
            client.complete([Message("user", "Hi")])


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("type", "other"),
        ("model", None),
        ("content", None),
        ("content", [{"type": "text", "text": None}]),
        ("content", [{"unexpected": "private body"}]),
        ("content", [{"type": "tool_use", "id": "tool", "name": "exec", "input": {}}]),
        ("usage", {"input_tokens": -1, "output_tokens": 30}),
        ("usage", {"input_tokens": "invalid", "output_tokens": 30}),
    ],
)
def test_invalid_response_data_is_rejected(key: str, value: object) -> None:
    body = response_body()
    body[key] = value
    with mock_client(lambda _: httpx2.Response(200, json=body)) as client:
        with pytest.raises(LLMResponseError):
            client.complete([Message("user", "Hi")])


def test_invalid_json_is_a_response_error() -> None:
    with mock_client(
        lambda _: httpx2.Response(200, text="private invalid JSON")
    ) as client:
        with pytest.raises(LLMResponseError) as error:
            client.complete([Message("user", "Hi")])
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    ("status", "error_type", "attempts"),
    [
        (400, LLMRequestError, 1),
        (401, LLMAuthenticationError, 1),
        (403, LLMAuthenticationError, 1),
        (404, LLMRequestError, 1),
        (408, LLMRequestError, 3),
        (409, LLMRequestError, 3),
        (413, LLMRequestError, 1),
        (422, LLMRequestError, 1),
        (429, LLMRateLimitError, 3),
        (500, LLMRequestError, 3),
        (503, LLMRequestError, 3),
        (529, LLMRequestError, 3),
    ],
)
def test_http_errors_and_retry_limits(
    status: int, error_type: type[LLMError], attempts: int
) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            status,
            json={"type": "error", "error": {"message": "private body with test-key"}},
            headers={"retry-after-ms": "1"},
        )

    with mock_client(handler) as client:
        with pytest.raises(error_type) as error:
            client.complete([Message("user", "private prompt")])
    assert len(requests) == attempts
    assert "private" not in str(error.value)
    assert "test-key" not in str(error.value)
    assert error.value.__suppress_context__


def test_retry_recovers_from_rate_limit() -> None:
    attempts = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx2.Response(429, json={}, headers={"retry-after-ms": "1"})
        return httpx2.Response(200, json=response_body())

    with mock_client(handler) as client:
        assert client.complete([Message("user", "Hi")]).text == "こんにちは！"
    assert attempts == 2


@pytest.mark.parametrize(
    ("transport_error", "error_type"),
    [(httpx2.ReadTimeout, LLMTimeoutError), (httpx2.ConnectError, LLMConnectionError)],
)
def test_transport_errors_are_converted(
    transport_error: type[httpx2.TransportError], error_type: type[LLMError]
) -> None:
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise transport_error("private transport detail", request=request)

    with mock_client(handler, config=AnthropicConfig(max_retries=0)) as client:
        with pytest.raises(error_type) as error:
            client.complete([Message("user", "Hi")])
    assert "private" not in str(error.value)
    assert attempts == 1


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [Message("system", "Be helpful")],
        [Message("assistant", "Hello")],
        [Message("user", "Hi"), Message("assistant", "Hello")],
    ],
)
def test_invalid_history_is_rejected_before_request(messages: list[Message]) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        pytest.fail("Invalid history must not cause an API request.")

    with mock_client(handler) as client:
        with pytest.raises(ValueError):
            client.complete(messages)


@pytest.mark.parametrize("limit", [0, -1, True])
def test_invalid_output_budget_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="max_output_tokens"):
        AnthropicConfig(max_output_tokens=limit)


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        AnthropicConfig(timeout_seconds=timeout)


def test_invalid_retry_count_and_model_are_rejected() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        AnthropicConfig(max_retries=-1)
    with pytest.raises(ValueError, match="Model"):
        AnthropicConfig(model=" \n ")


def test_sdk_lifetime_and_original_options_remain_with_caller() -> None:
    transport = httpx2.MockTransport(
        lambda _: httpx2.Response(200, json=response_body())
    )
    with httpx2.Client(transport=transport) as http:
        with Anthropic(
            api_key="test-key", http_client=http, timeout=75, max_retries=0
        ) as sdk:
            client = AnthropicClient(sdk)
            client.complete([Message("user", "Hi")])
            assert not sdk.is_closed()
            assert sdk.timeout == 75
            assert sdk.max_retries == 0
        assert http.is_closed
