"""実SDKの履歴と、失敗→再修正→再テストを固定課題で検証する。"""

import json
from pathlib import Path

import httpx2
import pytest

from coding_agent import client_repair as client
from coding_agent.repair_exercise import BROKEN, Exercise
from tests.test_tool_use import MockSDK, body


def call(name: str, arguments: object, index: int) -> dict[str, object]:
    return {"type": "tool_use", "id": f"tool_{index}", "name": name, "input": arguments}


def edit(old: str, new: str, index: int) -> dict[str, object]:
    return call(
        "Edit",
        {"file_path": "calculator.py", "old_string": old, "new_string": new},
        index,
    )


def plan() -> list[list[dict[str, object]]]:
    return [
        [
            {"type": "text", "text": "Investigating."},
            call("Read", {"file_path": "calculator.py"}, 0),
        ],
        [edit("a - b", "a * b", 1)],
        [call("run_tests", {}, 2)],
        [edit("a * b", "a + b", 3)],
        [call("run_tests", {}, 4)],
        [{"type": "text", "text": "Fixed and tested."}],
    ]


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 6])
def test_repair_failed_test_recovery_and_limits(mock_sdk: MockSDK, limit: int) -> None:
    contents = plan()
    count = 0
    previous_messages: list[object] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count, previous_messages
        payload = json.loads(request.content)
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["tool_choice"]["disable_parallel_tool_use"] is True
        assert payload["max_tokens"] == 4096
        assert [t["name"] for t in payload["tools"]] == ["Read", "Edit", "run_tests"]
        messages = payload["messages"]
        assert len(messages) == 1 + 2 * count
        if count:
            assert messages[:-2] == previous_messages
            assert messages[-2] == {"role": "assistant", "content": contents[count - 1]}
            tool_result = messages[-1]["content"][0]
            assert tool_result["tool_use_id"] == f"tool_{count - 1}"
            assert tool_result["is_error"] is False
            output = json.loads(tool_result["content"])
            if count == 1:
                assert output["text"] == BROKEN
            if count == 3:
                assert output["returncode"] != 0
                assert "FAILED" in output["output"]
            if count == 5:
                assert output["returncode"] == 0
                assert "Ran 4 tests" in output["output"]
        previous_messages = messages
        content = contents[count]
        count += 1
        return httpx2.Response(
            200, json=body(content, "end_turn" if count == 6 else "tool_use")
        )

    mock_sdk(handler)
    if limit < 6:
        with pytest.raises(ValueError, match="max_steps"):
            client.repair(max_steps=limit)
    else:
        answer = client.repair(max_steps=limit)
        assert "テスト実行: 2回" in answer
        assert "-    return a - b" in answer
        assert "+    return a + b" in answer
    assert count == limit


def test_denied_operation_can_recover(mock_sdk: MockSDK) -> None:
    count = 0
    contents: list[list[dict[str, object]]] = [
        [call("Read", {"file_path": "/etc/passwd"}, 0)],
        [edit("a - b", "a + b", 1)],
        [call("run_tests", {}, 2)],
        [{"type": "text", "text": "done"}],
    ]

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        payload = json.loads(request.content)
        if count == 1:
            result = payload["messages"][-1]["content"][0]
            assert result["is_error"] is True
            assert json.loads(result["content"]) == {"error": "Operation denied."}
        content = contents[count]
        count += 1
        return httpx2.Response(
            200, json=body(content, "end_turn" if count == 4 else "tool_use")
        )

    mock_sdk(handler)
    assert "固定テスト4件成功" in client.repair()


@pytest.mark.parametrize("scenario", ["untested", "stale"])
def test_final_claim_requires_current_passing_tests(
    mock_sdk: MockSDK, scenario: str
) -> None:
    contents = [[edit("a - b", "a + b", 0)]]
    if scenario == "stale":
        contents += [[call("run_tests", {}, 1)], [edit("a + b", "a * b", 2)]]
    contents += [[{"type": "text", "text": "All tests pass."}]]
    count = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        content = contents[count]
        count += 1
        return httpx2.Response(
            200,
            json=body(content, "end_turn" if count == len(contents) else "tool_use"),
        )

    mock_sdk(handler)
    with pytest.raises(ValueError, match="no verified"):
        client.repair()


@pytest.mark.parametrize(
    "stop,content",
    [
        ("max_tokens", [{"type": "text", "text": "partial"}]),
        ("end_turn", [{"type": "text", "text": " "}]),
        ("tool_use", [call("run_tests", {}, 0), call("run_tests", {}, 1)]),
        ("end_turn", [call("run_tests", {}, 0)]),
    ],
)
def test_invalid_response_stops_without_more_requests(
    mock_sdk: MockSDK, stop: str, content: list[dict[str, object]]
) -> None:
    count = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(200, json=body(content, stop))

    mock_sdk(handler)
    with pytest.raises(ValueError, match="incomplete"):
        client.repair()
    assert count == 1


def test_api_error_stops_and_main_hides_details(
    mock_sdk: MockSDK, capsys: pytest.CaptureFixture[str]
) -> None:
    count = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return httpx2.Response(
            401,
            json={
                "error": {"type": "authentication_error", "message": "private-secret"}
            },
        )

    mock_sdk(handler)
    with pytest.raises(SystemExit, match="Repair stopped") as error:
        client.main()
    captured = capsys.readouterr()
    assert not captured.out
    assert "private" not in str(error.value) + captured.err
    assert count == 1


@pytest.mark.parametrize("limit", [0, -1, 21, True])
def test_invalid_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="max_steps"):
        client.repair(max_steps=limit)


def test_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", " ")
    with pytest.raises(ValueError, match="LLM_MODEL"):
        client.repair()


def test_tool_validation_and_test_limit(tmp_path: Path) -> None:
    exercise = Exercise(tmp_path / "project")
    for name, arguments in [
        ("Bash", {"command": "anything"}),
        ("Read", None),
        (
            "Edit",
            {"file_path": "test_calculator.py", "old_string": "42", "new_string": "0"},
        ),
        (
            "Edit",
            {
                "file_path": "calculator.py",
                "old_string": "a - b",
                "new_string": "eval('private')",
            },
        ),
    ]:
        assert client.execute(exercise, name, arguments) == {
            "error": "Operation denied."
        }
    for _ in range(4):
        assert client.execute(exercise, "run_tests", {})["returncode"] != 0
    assert client.execute(exercise, "run_tests", {}) == {"error": "Operation denied."}
    assert exercise.source() == BROKEN
