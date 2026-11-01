"""SDKを直接使う実行例の、要求設定と表示・終了の判断を検証する。"""

import json
from collections.abc import Callable, Iterator

import anthropic
import httpx2
import pytest

from coding_agent import llm


def response_body(model: str = "claude-haiku-5-5") -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": "こんにちは！"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 30},
    }


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


@pytest.mark.parametrize("model", [None, "claude-sonnet-5-5"])
def test_sdk_request_and_output(
    model: str | None,
    monkeypatch: pytest.MonkeyPatch,
    mock_sdk: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    if model is not None:
        monkeypatch.setenv("LLM_MODEL", model)
    expected_model = model or "claude-haiku-5-5"
    requests: list[httpx2.Request] = []
    body = response_body(expected_model)
    body["content"] = [
        {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
        {"type": "text", "text": "前半\n"},
        {"type": "redacted_thinking", "data": "private data"},
        {"type": "text", "text": "後半"},
    ]

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert json.loads(request.content) == {
            "model": expected_model,
            "max_tokens": 16_000,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"},
            "messages": [{"role": "user", "content": "PythonのProtocolを短く説明して"}],
            "stream": False,
        }
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 30.0
        )
        return httpx2.Response(200, json=body)

    mock_sdk(handler)
    llm.main()
    captured = capsys.readouterr()
    assert captured.out == "前半\n後半\n"
    assert f"model: {expected_model}" in captured.err
    assert "stop_reason: end_turn" in captured.err
    assert "input_tokens=10" in captured.err
    assert "output_tokens=30" in captured.err
    assert "private" not in captured.out + captured.err
    assert len(requests) == 1


@pytest.mark.parametrize(
    "reason", ["max_tokens", "model_context_window_exceeded", "refusal", "tool_use"]
)
def test_incomplete_response_keeps_metadata_without_printing_partial_text(
    reason: str,
    mock_sdk: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = response_body()
    body["stop_reason"] = reason
    attempts = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(200, json=body)

    mock_sdk(handler)
    with pytest.raises(SystemExit, match="did not finish normally"):
        llm.main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"stop_reason: {reason}" in captured.err
    assert "model: claude-haiku-5-5" in captured.err
    assert "output_tokens=30" in captured.err
    assert attempts == 1


@pytest.mark.parametrize("text", ["", " \n "])
def test_empty_text_is_not_a_success(
    text: str,
    mock_sdk: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = response_body()
    body["content"] = [{"type": "text", "text": text}]
    mock_sdk(lambda _: httpx2.Response(200, json=body))
    with pytest.raises(SystemExit, match="contained no text"):
        llm.main()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("status", "error_name", "expected_attempts"),
    [(401, "AuthenticationError", 1), (429, "RateLimitError", 3)],
)
def test_sdk_errors_have_safe_display_and_no_outer_retry(
    status: int,
    error_name: str,
    expected_attempts: int,
    mock_sdk: Callable[[Callable[[httpx2.Request], httpx2.Response]], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    attempts = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(
            status,
            json={"type": "error", "error": {"message": "private test-key"}},
            headers={"retry-after-ms": "1"},
        )

    mock_sdk(handler)
    with pytest.raises(SystemExit) as error:
        llm.main()
    assert str(error.value) == f"Claude SDK error ({error_name})."
    assert error.value.__suppress_context__
    assert capsys.readouterr().out == ""
    assert attempts == expected_attempts


def test_empty_model_does_not_open_a_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", " \n ")

    def unexpected_client(**kwargs: object) -> None:
        pytest.fail("Empty model must not open a connection.")

    monkeypatch.setattr(anthropic, "Anthropic", unexpected_client)
    with pytest.raises(SystemExit, match="LLM_MODEL must not be empty"):
        llm.main()
