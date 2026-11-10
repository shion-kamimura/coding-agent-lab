"""Tool Runnerの公開APIを使う、小さなオフライン比較例。"""

import json

import anthropic
import httpx2
import pytest
from anthropic import beta_tool
from anthropic.types.beta import BetaMessage

from coding_agent import tool_use
from tests.test_tool_use import MockSDK, body, call


@pytest.mark.parametrize("scenario", ["round_trip", "limit", "failure", "max_tokens"])
def test_runner_comparison(mock_sdk: MockSDK, scenario: str) -> None:
    executed: list[tuple[int, int]] = []

    @beta_tool
    def add(a: int, b: int) -> str:
        """Add two integers and return their sum."""
        executed.append((a, b))
        if scenario == "failure":
            raise ValueError("synthetic comparison failure")
        return str(tool_use.add(a, b))

    requests: list[dict[str, object]] = []
    contents: list[list[dict[str, object]]] = [
        [call()],
        [dict(call({"a": 42, "b": 8}), id="tool_second")],
        [{"type": "text", "text": "50"}],
    ]
    expected: list[dict[str, object]] = [
        {"role": "user", "content": "17と25を足し、その結果に8を足して"}
    ]

    def handler(request: httpx2.Request) -> httpx2.Response:
        payload = json.loads(request.content)
        index = len(requests)
        requests.append(payload)
        if scenario in {"round_trip", "limit"}:
            assert payload["messages"] == expected
            content = contents[index]
            if index < 2:
                expected.extend(
                    [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": ["tool_123", "tool_second"][index],
                                    "content": ["42", "50"][index],
                                }
                            ],
                        },
                    ]
                )
            return httpx2.Response(
                200, json=body(content, "end_turn" if index == 2 else "tool_use")
            )
        if scenario == "max_tokens":
            return httpx2.Response(
                200, json=body([{"type": "text", "text": "partial"}], "max_tokens")
            )
        if index == 0:
            return httpx2.Response(200, json=body([call()], "tool_use"))
        messages = payload["messages"]
        result = messages[-1]["content"][0]
        assert result["is_error"] is True
        assert "synthetic comparison failure" in str(result["content"])
        return httpx2.Response(
            200, json=body([{"type": "text", "text": "failed"}], "end_turn")
        )

    mock_sdk(handler)
    with anthropic.Anthropic(timeout=30.0, max_retries=2) as client:
        runner = client.beta.messages.tool_runner(
            model="claude-haiku-5-5",
            max_tokens=16_000,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": "17と25を足し、その結果に8を足して"}],
            tools=[add],
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            max_iterations=2 if scenario == "limit" else 3,
            stream=False,
            thread=False,
        )
        responses: list[BetaMessage] = list(runner)
    if scenario == "round_trip":
        assert executed == [(17, 25), (42, 8)]
        assert len(requests) == len(responses) == 3
        assert responses[-1].stop_reason == "end_turn"
    elif scenario == "limit":
        assert len(requests) == len(responses) == 2
        assert responses[-1].stop_reason == "tool_use"
        # 上限の応答に含まれるツールも実行されるが、次のAPI要求は行わない。
        assert executed == [(17, 25), (42, 8)]
    elif scenario == "failure":
        assert len(requests) == 2
        assert executed == [(17, 25)]
    else:
        assert len(requests) == 1
        assert executed == []
        assert responses[-1].stop_reason == "max_tokens"
