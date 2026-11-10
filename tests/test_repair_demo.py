"""実モデルなしで操作境界・固定テスト・完了判定を確認する。"""

import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    SdkMcpTool,
    create_sdk_mcp_server,
)
from claude_agent_sdk.types import McpSdkServerConfig, PreToolUseHookInput

from coding_agent import repair_demo as demo

FIXED = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def exercise(tmp_path: Path) -> demo.Exercise:
    return demo.Exercise(tmp_path / "project")


def result(*, error: bool = False) -> ResultMessage:
    return ResultMessage(
        subtype="error_max_turns" if error else "success",
        is_error=error,
        duration_ms=1,
        duration_api_ms=1,
        num_turns=3,
        session_id="test-session",
    )


@pytest.mark.parametrize(
    "source",
    [
        "import os\n" + FIXED,
        "def add(a, b):\n    return __import__('os').getenv('PRIVATE')\n",
        "def add(a, b):\n    return a ** b\n",
        "def add(a, b=open('private')):\n    return a + b\n",
        "@print('private')\n" + FIXED,
        FIXED + "print('private')\n",
        "# coding: unicode_escape\n# \\nraise RuntimeError('private')\n" + FIXED,
        "def add(a, b):\n    while True: pass\n",
        "syntax error",
        " " * 4097,
    ],
)
def test_executable_source_is_limited(source: str) -> None:
    with pytest.raises(ValueError, match="Denied"):
        demo.check_source(source)


def test_real_fixed_tests_and_diff(exercise: demo.Exercise) -> None:
    assert exercise.run_tests()["returncode"] != 0
    (exercise.root / "calculator.py").write_text(FIXED)
    exercise.test_runs = 1
    assert exercise.run_tests()["returncode"] == 0
    diff = exercise.verified_diff(result())
    assert "-    return a - b" in diff
    assert "+    return a + b" in diff
    assert (exercise.root / "test_calculator.py").read_text() == demo.TESTS


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("Bash", {"command": "python test_calculator.py"}),
        ("Write", {"file_path": "calculator.py", "content": FIXED}),
        ("Read", {"file_path": "../private"}),
        ("Read", {"file_path": "/etc/passwd"}),
        (
            "Edit",
            {"file_path": "test_calculator.py", "old_string": "42", "new_string": "0"},
        ),
        ("Edit", {"file_path": "calculator.py", "old_string": "", "new_string": FIXED}),
        (
            "Edit",
            {
                "file_path": "calculator.py",
                "old_string": "a - b",
                "new_string": "a + b",
                "replace_all": True,
            },
        ),
        (demo.TEST_TOOL, {"command": "anything"}),
    ],
)
def test_hook_denies_out_of_scope(
    exercise: demo.Exercise, name: str, arguments: dict[str, Any]
) -> None:
    data: PreToolUseHookInput = {
        "session_id": "test-session",
        "transcript_path": "unused",
        "cwd": str(exercise.root),
        "hook_event_name": "PreToolUse",
        "tool_name": name,
        "tool_input": arguments,
        "tool_use_id": "test-tool",
    }
    response = asyncio.run(exercise.gate(data, None, {"signal": None}))
    specific = response.get("hookSpecificOutput")
    assert isinstance(specific, dict)
    assert specific.get("permissionDecision") == "deny"


def test_edit_and_read_permissions(exercise: demo.Exercise) -> None:
    assert exercise.permits("Read", {"file_path": "test_calculator.py"})
    assert exercise.permits(
        "Edit",
        {"file_path": "calculator.py", "old_string": "a - b", "new_string": "a + b"},
    )
    with pytest.raises(ValueError, match="Denied"):
        exercise.permits(
            "Edit",
            {
                "file_path": "calculator.py",
                "old_string": "a - b",
                "new_string": "eval('private')",
            },
        )
    exercise.test_runs = 4
    assert not exercise.permits(demo.TEST_TOOL, {})


def test_hook_failure_denies_without_exception_details(
    exercise: demo.Exercise, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(name: str, arguments: dict[str, Any]) -> bool:
        raise RuntimeError("private-secret")

    monkeypatch.setattr(exercise, "permits", fail)
    data: PreToolUseHookInput = {
        "session_id": "test-session",
        "transcript_path": "unused",
        "cwd": str(exercise.root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "calculator.py"},
        "tool_use_id": "test-tool",
    }
    response = asyncio.run(exercise.gate(data, None, {"signal": None}))
    specific = response.get("hookSpecificOutput")
    assert isinstance(specific, dict)
    assert specific.get("permissionDecision") == "deny"
    assert "private" not in str(response)


@pytest.mark.parametrize("change", ["tests", "link"])
def test_modified_or_symlinked_tests_are_not_executed(
    exercise: demo.Exercise, change: str
) -> None:
    tests = exercise.root / "test_calculator.py"
    if change == "link":
        tests.unlink()
        tests.symlink_to(exercise.root / "calculator.py")
    else:
        tests.write_text("raise SystemExit(0)\n")
    with pytest.raises(ValueError, match="Denied"):
        exercise.run_tests()


@pytest.mark.parametrize(
    "condition", ["unchanged", "untested", "stale", "error", "missing", "failed"]
)
def test_completion_requires_observed_passing_tests(
    exercise: demo.Exercise, condition: str
) -> None:
    if condition != "unchanged":
        (exercise.root / "calculator.py").write_text(FIXED)
    exercise.test_runs = 0 if condition == "untested" else 1
    exercise.run_tests()
    if condition == "stale":
        (exercise.root / "calculator.py").write_text(
            "def add(a, b):\n    return (a + b)\n"
        )
    if condition == "failed":
        exercise.last_returncode = 1
    final = None if condition == "missing" else result(error=condition == "error")
    with pytest.raises(ValueError, match="incomplete"):
        exercise.verified_diff(final)


def test_test_process_has_no_credentials_and_has_timeout(
    exercise: demo.Exercise, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == [
            sys.executable,
            "-I",
            "-B",
            str(exercise.root / "test_calculator.py"),
        ]
        assert kwargs["env"] == {}
        assert kwargs["timeout"] == 5
        assert "shell" not in kwargs
        raise subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        exercise.run_tests()


def test_sdk_wiring_and_test_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[SdkMcpTool[Any]] = []
    roots: list[Path] = []

    def server(*, name: str, tools: list[SdkMcpTool[Any]]) -> McpSdkServerConfig:
        captured.extend(tools)
        return create_sdk_mcp_server(name=name, tools=tools)

    class Client:
        def __init__(self, *, options: ClaudeAgentOptions) -> None:
            assert options.tools == ["Read", "Edit"]
            assert options.allowed_tools == []
            assert options.setting_sources == []
            assert options.strict_mcp_config
            assert options.skills == []
            assert options.max_turns == 8
            assert options.max_budget_usd == 0.25
            assert options.hooks and options.hooks["PreToolUse"]
            assert isinstance(options.cwd, Path)
            self.root = options.cwd
            roots.append(self.root)

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            pass

        async def query(self, prompt: str) -> None:
            assert "加算" in prompt

        async def receive_response(self) -> AsyncIterator[ResultMessage]:
            (self.root / "calculator.py").write_text(FIXED)
            assert (await captured[0].handler({"command": "bad"}))["is_error"]

            def fail_test(self: demo.Exercise) -> dict[str, object]:
                raise RuntimeError("private-secret")

            with monkeypatch.context() as context:
                context.setattr(demo.Exercise, "run_tests", fail_test)
                failure = await captured[0].handler({})
                assert failure["is_error"]
                assert "private" not in str(failure)
            for _ in range(3):
                output = await captured[0].handler({})
                assert "is_error" not in output
                assert '"returncode": 0' in output["content"][0]["text"]
            assert (await captured[0].handler({}))["is_error"]
            yield result()

    monkeypatch.setattr(demo, "create_sdk_mcp_server", server)
    monkeypatch.setattr(demo, "ClaudeSDKClient", Client)
    answer = asyncio.run(demo.repair())
    assert "固定テスト4件成功" in answer
    assert "テスト実行: 4回" in answer
    assert not roots[0].exists()


@pytest.mark.parametrize("max_turns", [0, -1, 21, True])
def test_invalid_limits_fail_before_sdk(max_turns: int) -> None:
    with pytest.raises(ValueError, match="max_turns"):
        asyncio.run(demo.repair(max_turns=max_turns))


def test_empty_model_fails_before_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", " ")
    with pytest.raises(ValueError, match="LLM_MODEL"):
        asyncio.run(demo.repair())


def test_main_hides_sdk_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fail() -> str:
        raise RuntimeError("private-secret")

    monkeypatch.setattr(demo, "repair", fail)
    with pytest.raises(SystemExit, match="Repair stopped") as error:
        demo.main()
    assert "private" not in str(error.value)
    assert not capsys.readouterr().out
