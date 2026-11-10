"""実SDKの模擬通信で履歴・停止・失敗の境界を検証する。"""

import json

import anthropic
import httpx2
import pytest

from coding_agent import agent_loop, tool_use
from tests.test_tool_use import MockSDK, body, call


def test_sequential_history(
    mock_sdk: MockSDK,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5-5")
    contents: list[list[dict[str, object]]] = [
        [{"type": "text", "text": "途中"}, call()],
        [dict(call({"a": 42, "b": 8}), id="tool_second")],
        [
            {"type": "thinking", "thinking": "private", "signature": "sig"},
            {"type": "text", "text": "答えは"},
            {"type": "text", "text": "50です。"},
        ],
    ]
    expected: list[dict[str, object]] = [
        {"role": "user", "content": "17と25を足し、その結果に8を足して"}
    ]
    count = 0
    executed: list[tuple[int, int]] = []

    def add(a: int, b: int) -> int:
        executed.append((a, b))
        return a + b

    monkeypatch.setattr(tool_use, "add", add)

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        payload = json.loads(request.content)
        assert payload["messages"] == expected
        assert payload["model"] == "claude-sonnet-5-5"
        assert payload["tools"] == [tool_use.ADD_TOOL]
        assert payload["tool_choice"] == {
            "type": "auto",
            "disable_parallel_tool_use": True,
        }
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["max_tokens"] == 16_000
        assert payload["stream"] is False
        content = contents[count]
        if count < 2:
            expected.extend(
                [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": ["tool_123", "tool_second"][count],
                                "content": ["42", "50"][count],
                            }
                        ],
                    },
                ]
            )
        count += 1
        return httpx2.Response(
            200, json=body(content, "end_turn" if count == 3 else "tool_use")
        )

    mock_sdk(handler)
    agent_loop.main(max_steps=3)
    captured = capsys.readouterr()
    assert captured.out == "答えは50です。\n"
    assert "private" not in captured.out + captured.err
    assert "途中" not in captured.out + captured.err
    assert captured.err.count("input_tokens=10") == 3
    assert "step: 3/3" in captured.err
    assert count == 3
    assert executed == [(17, 25), (42, 8)]


@pytest.mark.parametrize("limit", [1, 2, 5])
def test_limit(
    mock_sdk: MockSDK, limit: int, capsys: pytest.CaptureFixture[str]
) -> None:
    count = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(200, json=body([call()], "tool_use"))

    mock_sdk(handler)
    with pytest.raises(SystemExit, match="incomplete: max_steps"):
        agent_loop.main(max_steps=limit)
    assert count == limit
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "3", None])
def test_invalid_limit(limit: object, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(**kwargs: object) -> None:
        pytest.fail("Invalid limits must not open a client.")

    monkeypatch.setattr(anthropic, "Anthropic", unexpected)
    with pytest.raises(SystemExit, match="positive integer"):
        agent_loop.main(max_steps=limit)  # type: ignore[arg-type]


def test_direct_answer(mock_sdk: MockSDK, capsys: pytest.CaptureFixture[str]) -> None:
    count = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(
            200, json=body([{"type": "text", "text": "50"}], "end_turn")
        )

    mock_sdk(handler)
    agent_loop.main(max_steps=1)
    assert count == 1
    assert capsys.readouterr().out == "50\n"


@pytest.mark.parametrize("stage", [1, 2])
@pytest.mark.parametrize(
    "content,stop",
    [
        ([call({"a": True, "b": 8})], "tool_use"),
        ([call({"a": 1.5, "b": 8})], "tool_use"),
        ([call({"a": "42", "b": 8})], "tool_use"),
        ([call({"a": 42})], "tool_use"),
        ([call({"a": 42, "b": 8, "c": 1})], "tool_use"),
        ([call([])], "tool_use"),
        ([call(name="unknown")], "tool_use"),
        ([], "tool_use"),
        ([call(), call()], "tool_use"),
        ([call(), {"type": "text", "text": "partial"}], "end_turn"),
        ([], "end_turn"),
        ([{"type": "text", "text": " \n"}], "end_turn"),
        *[
            ([{"type": "text", "text": "partial"}], reason)
            for reason in [
                "max_tokens",
                "refusal",
                "model_context_window_exceeded",
                "pause_turn",
                "stop_sequence",
            ]
        ],
    ],
)
def test_invalid_response(
    stage: int,
    content: list[dict[str, object]],
    stop: str,
    mock_sdk: MockSDK,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    count = 0
    executed = 0

    def add(a: int, b: int) -> int:
        nonlocal executed
        executed += 1
        return a + b

    monkeypatch.setattr(tool_use, "add", add)

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(
            200,
            json=(body([call()], "tool_use") if count < stage else body(content, stop)),
        )

    mock_sdk(handler)
    with pytest.raises(SystemExit):
        agent_loop.main()
    assert count == stage
    assert executed == stage - 1
    assert capsys.readouterr().out == ""


def test_tool_failure(
    mock_sdk: MockSDK,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    count = 0

    def broken(a: int, b: int) -> int:
        raise RuntimeError("private test-key")

    monkeypatch.setattr(tool_use, "add", broken)

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(200, json=body([call()], "tool_use"))

    mock_sdk(handler)
    with pytest.raises(SystemExit, match="add execution failed") as error:
        agent_loop.main()
    assert error.value.__suppress_context__
    assert count == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private" not in captured.err


@pytest.mark.parametrize("stage", [1, 2, 3])
@pytest.mark.parametrize(
    "status,name,retries",
    [
        (401, "AuthenticationError", 1),
        (429, "RateLimitError", 3),
    ],
)
def test_sdk_error(
    stage: int,
    status: int,
    name: str,
    retries: int,
    mock_sdk: MockSDK,
    capsys: pytest.CaptureFixture[str],
) -> None:
    count = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        if count < stage:
            return httpx2.Response(200, json=body([call()], "tool_use"))
        return httpx2.Response(
            status,
            json={"type": "error", "error": {"message": "private test-key"}},
            headers={"retry-after-ms": "1"},
        )

    mock_sdk(handler)
    with pytest.raises(SystemExit) as error:
        agent_loop.main()
    assert str(error.value) == f"Claude SDK error ({name})."
    assert error.value.__suppress_context__
    assert count == stage - 1 + retries
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private" not in captured.err


def test_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", " \n")

    def unexpected(**kwargs: object) -> None:
        pytest.fail("Empty model must not open a client.")

    monkeypatch.setattr(anthropic, "Anthropic", unexpected)
    with pytest.raises(SystemExit, match="LLM_MODEL must not be empty"):
        agent_loop.main()
