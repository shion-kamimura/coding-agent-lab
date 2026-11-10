"""2要求の履歴・実行・出力と、異常時の停止を模擬HTTPで確認する。"""

import json
from collections.abc import Callable

import anthropic
import httpx2
import pytest

from coding_agent import tool_use

MockSDK = Callable[[Callable[[httpx2.Request], httpx2.Response]], None]


def body(content: list[dict[str, object]], stop: str) -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": content,
        "stop_reason": stop,
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }


def call(arguments: object = None, name: str = "add") -> dict[str, object]:
    return {
        "type": "tool_use",
        "id": "tool_123",
        "name": name,
        "input": {"a": 17, "b": 25} if arguments is None else arguments,
    }


@pytest.mark.parametrize("model", [None, "claude-sonnet-5-5"])
def test_round_trip(
    mock_sdk: MockSDK,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    model: str | None,
) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    if model:
        monkeypatch.setenv("LLM_MODEL", model)
    requests: list[dict[str, object]] = []
    content: list[dict[str, object]] = [{"type": "text", "text": "計算します"}, call()]
    executed: list[tuple[int, int]] = []
    original_add = tool_use.add

    def add(a: int, b: int) -> int:
        executed.append((a, b))
        return original_add(a, b)

    monkeypatch.setattr(tool_use, "add", add)

    def handler(request: httpx2.Request) -> httpx2.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == (model or "claude-haiku-5-5")
        assert payload["tools"] == [tool_use.ADD_TOOL]
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["max_tokens"] == 16_000
        assert payload["stream"] is False
        if len(requests) == 1:
            assert payload["tool_choice"] == {
                "type": "tool",
                "name": "add",
                "disable_parallel_tool_use": True,
            }
            assert payload["messages"] == [
                {"role": "user", "content": "17と25を足して"}
            ]
            return httpx2.Response(200, json=body(content, "tool_use"))
        assert payload["tool_choice"] == {"type": "none"}
        assert payload["messages"] == [
            {"role": "user", "content": "17と25を足して"},
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool_123", "content": "42"}
                ],
            },
        ]
        return httpx2.Response(
            200,
            json=body(
                [
                    {"type": "thinking", "thinking": "private", "signature": "sig"},
                    {"type": "text", "text": "答えは"},
                    {"type": "text", "text": "42です。"},
                ],
                "end_turn",
            ),
        )

    mock_sdk(handler)
    tool_use.main()
    captured = capsys.readouterr()
    assert captured.out == "答えは42です。\n"
    assert "private" not in captured.out + captured.err
    assert "計算します" not in captured.out
    assert "stop_reason: tool_use" in captured.err
    assert "stop_reason: end_turn" in captured.err
    assert captured.err.count("input_tokens=10") == 2
    assert len(requests) == 2
    assert executed == [(17, 25)]


@pytest.mark.parametrize(
    "content,stop",
    [
        ([call({"a": True, "b": 25})], "tool_use"),
        ([call({"a": 1.5, "b": 25})], "tool_use"),
        ([call({"a": "17", "b": 25})], "tool_use"),
        ([call({"a": 17})], "tool_use"),
        ([call({"a": 17, "b": 25, "c": 1})], "tool_use"),
        ([call([])], "tool_use"),
        ([call(name="unknown")], "tool_use"),
        ([], "tool_use"),
        ([call(), call()], "tool_use"),
        ([call()], "max_tokens"),
        ([call()], "end_turn"),
    ],
)
def test_invalid_first_response(
    content: list[dict[str, object]],
    stop: str,
    mock_sdk: MockSDK,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attempts = 0

    def unexpected_add(a: int, b: int) -> int:
        pytest.fail("Invalid calls must not execute.")

    monkeypatch.setattr(tool_use, "add", unexpected_add)

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(200, json=body(content, stop))

    mock_sdk(handler)
    with pytest.raises(SystemExit):
        tool_use.main()
    assert attempts == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "content,stop",
    [
        ([{"type": "text", "text": "partial"}], reason)
        for reason in [
            "max_tokens",
            "refusal",
            "model_context_window_exceeded",
            "tool_use",
        ]
    ]
    + [
        ([], "end_turn"),
        ([{"type": "text", "text": " \n"}], "end_turn"),
        ([call(), {"type": "text", "text": "42"}], "end_turn"),
    ],
)
def test_invalid_final_response(
    content: list[dict[str, object]],
    stop: str,
    mock_sdk: MockSDK,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attempts = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(
            200,
            json=body([call()], "tool_use") if attempts == 1 else body(content, stop),
        )

    mock_sdk(handler)
    with pytest.raises(SystemExit):
        tool_use.main()
    assert attempts == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("stage", [1, 2])
@pytest.mark.parametrize(
    "status,error_name,retries",
    [
        (401, "AuthenticationError", 1),
        (429, "RateLimitError", 3),
    ],
)
def test_safe_sdk_error(
    stage: int,
    status: int,
    error_name: str,
    retries: int,
    mock_sdk: MockSDK,
    capsys: pytest.CaptureFixture[str],
) -> None:
    attempts = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if stage == 2 and attempts == 1:
            return httpx2.Response(200, json=body([call()], "tool_use"))
        return httpx2.Response(
            status,
            json={"type": "error", "error": {"message": "private test-key"}},
            headers={"retry-after-ms": "1"},
        )

    mock_sdk(handler)
    with pytest.raises(SystemExit) as error:
        tool_use.main()
    assert str(error.value) == f"Claude SDK error ({error_name})."
    assert error.value.__suppress_context__
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private" not in captured.err
    assert attempts == retries + stage - 1


def test_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", " \n")

    def unexpected_client(**kwargs: object) -> None:
        pytest.fail("Empty model must not connect.")

    monkeypatch.setattr(anthropic, "Anthropic", unexpected_client)
    with pytest.raises(SystemExit, match="LLM_MODEL must not be empty"):
        tool_use.main()
