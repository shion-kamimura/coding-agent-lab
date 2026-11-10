"""Agent SDKで、一時的な算術課題を編集して固定テストを確認する学習例。"""

import ast
import asyncio
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk.types import HookContext, HookInput, HookJSONOutput

BROKEN = "def add(a, b):\n    return a - b\n"
TESTS = """import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from calculator import add

class AdditionTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add(17, 25), 42)

    def test_mixed(self):
        self.assertEqual(add(-3, 5), 2)

    def test_zero(self):
        self.assertEqual(add(0, 0), 0)

    def test_negative(self):
        self.assertEqual(add(-5, -2), -7)

if __name__ == "__main__":
    unittest.main()
"""
TEST_TOOL = "mcp__checks__run_tests"


def check_source(source: str) -> None:
    """実行可能な課題はadd(a,b)の単一算術式だけ。汎用Pythonではない。"""
    if len(source.encode("utf-8")) > 4096:
        raise ValueError("Denied: source too large.")
    try:
        # Match the parser used for importing the actual UTF-8 file, including
        # encoding cookies. Parsing a str alone could overlook a different codec.
        tree = ast.dump(ast.parse(source.encode("utf-8")))
    except SyntaxError:
        raise ValueError("Denied: invalid exercise source.") from None
    permitted = {
        ast.dump(ast.parse(f"def add(a, b):\n    return a {operator} b\n"))
        for operator in ("+", "-", "*")
    }
    if tree not in permitted:
        raise ValueError(
            "Denied: only the exercise's arithmetic expression is allowed."
        )


class Exercise:
    """アプリ所有の一時ファイル、操作境界と実テストの状態。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir()
        (root / "calculator.py").write_text(BROKEN, encoding="utf-8")
        (root / "test_calculator.py").write_text(TESTS, encoding="utf-8")
        self.test_runs = 0
        self.last_tested: str | None = None
        self.last_returncode: int | None = None

    def source(self) -> str:
        for name in ("calculator.py", "test_calculator.py"):
            path = self.root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Denied: exercise files must be regular files.")
        if (self.root / "test_calculator.py").read_text(encoding="utf-8") != TESTS:
            raise ValueError("Denied: fixed tests changed.")
        source = (self.root / "calculator.py").read_text(encoding="utf-8")
        check_source(source)
        return source

    def run_tests(self) -> dict[str, object]:
        source = self.source()
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(self.root / "test_calculator.py")],
            cwd=self.root,
            env={},
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.last_tested = source
        self.last_returncode = result.returncode
        return {"returncode": result.returncode, "output": result.stderr[-4096:]}

    def permits(self, name: str, arguments: dict[str, Any]) -> bool:
        if name == TEST_TOOL:
            return not arguments and self.test_runs < 4
        raw_path = arguments.get("file_path")
        if name not in {"Read", "Edit"} or not isinstance(raw_path, str):
            return False
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.root / path
        # No normalization of '..' and no symlink traversal are needed or allowed.
        if path not in {self.root / "calculator.py", self.root / "test_calculator.py"}:
            return False
        if path.is_symlink() or not path.is_file():
            return False
        if name == "Read":
            return set(arguments) <= {"file_path", "offset", "limit"}
        if path.name != "calculator.py":
            return False
        if set(arguments) - {"file_path", "old_string", "new_string", "replace_all"}:
            return False
        old, new = arguments.get("old_string"), arguments.get("new_string")
        if not isinstance(old, str) or not old or not isinstance(new, str):
            return False
        if arguments.get("replace_all", False) is not False:
            return False
        source = self.source()
        if source.count(old) != 1:
            return False
        check_source(source.replace(old, new, 1))
        return True

    async def gate(
        self, data: HookInput, tool_use_id: str | None, context: HookContext
    ) -> HookJSONOutput:
        permitted = False
        try:
            if data["hook_event_name"] == "PreToolUse":
                permitted = self.permits(data["tool_name"], data["tool_input"])
        except Exception:
            pass
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" if permitted else "deny",
                "permissionDecisionReason": "Only the fixed exercise is allowed.",
            }
        }

    def verified_diff(self, result: ResultMessage | None) -> str:
        source = self.source()
        if (
            result is None
            or result.is_error
            or result.subtype != "success"
            or source == BROKEN
            or self.test_runs == 0
            or self.last_tested != source
            or self.last_returncode != 0
        ):
            raise ValueError("Repair incomplete: no verified model test result.")
        if self.run_tests()["returncode"] != 0:
            raise ValueError("Repair incomplete: final tests failed.")
        return "".join(
            difflib.unified_diff(
                BROKEN.splitlines(keepends=True),
                source.splitlines(keepends=True),
                fromfile="before/calculator.py",
                tofile="after/calculator.py",
            )
        )


async def repair(*, max_turns: int = 8) -> str:
    """任意リポジトリは受け取らず、毎回新しい課題を生成する。"""
    if type(max_turns) is not int or not 1 <= max_turns <= 20:
        raise ValueError("max_turns must be an integer between 1 and 20.")
    model = os.environ.get("LLM_MODEL", "claude-haiku-5-5").strip()
    if not model:
        raise ValueError("LLM_MODEL must not be empty.")
    with TemporaryDirectory(prefix="coding-agent-exercise-") as directory:
        workspace = Path(directory)
        exercise = Exercise(workspace / "project")
        if exercise.run_tests()["returncode"] == 0:
            raise ValueError("Repair incomplete: baseline unexpectedly passed.")

        @tool("run_tests", "Run the fixed addition tests; no arguments.", {})
        async def run_tests(arguments: dict[str, Any]) -> dict[str, Any]:
            if arguments or exercise.test_runs >= 4:
                return {
                    "content": [
                        {"type": "text", "text": "Test limit or invalid input."}
                    ],
                    "is_error": True,
                }
            exercise.test_runs += 1
            try:
                result = await asyncio.to_thread(exercise.run_tests)
            except Exception:
                return {
                    "content": [{"type": "text", "text": "Tests could not run."}],
                    "is_error": True,
                }
            return {"content": [{"type": "text", "text": json.dumps(result)}]}

        options = ClaudeAgentOptions(
            model=model,
            cwd=exercise.root,
            tools=["Read", "Edit"],
            allowed_tools=[],
            permission_mode="default",
            setting_sources=[],
            skills=[],
            strict_mcp_config=True,
            mcp_servers={
                "checks": create_sdk_mcp_server(name="checks", tools=[run_tests])
            },
            hooks={"PreToolUse": [HookMatcher(hooks=[exercise.gate])]},
            max_turns=max_turns,
            max_budget_usd=0.25,
            thinking={"type": "disabled"},
            env={
                "CLAUDE_CONFIG_DIR": str(workspace / "config"),
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            },
            system_prompt=(
                "Fix the addition bug in calculator.py using Read and Edit. "
                "Only calculator.py and test_calculator.py may be read. "
                "Never edit tests. The exercise permits only def add(a, b) with "
                "one return expression: a + b, a - b, or a * b. "
                "Use run_tests after editing and inspect its actual result. "
                "No shell or other tools are available. Do not claim success without "
                "a passing test result for your final edit."
            ),
        )
        final: ResultMessage | None = None
        async with asyncio.timeout(120), ClaudeSDKClient(options=options) as client:
            await client.query("整数の加算関数を修正し、固定テストの成功を確認して。")
            async for message in client.receive_response():
                if isinstance(message, ResultMessage):
                    final = message
        diff = exercise.verified_diff(final)
        return (
            "修正前: 固定テスト失敗\n修正後: 固定テスト4件成功（アプリで再実行済み）\n"
            f"モデルからのテスト実行: {exercise.test_runs}回\n{diff}"
        )


def main() -> None:
    try:
        print(asyncio.run(repair()))
    except Exception:
        raise SystemExit(
            "Repair stopped: SDK, test, or verification failure."
        ) from None


if __name__ == "__main__":
    main()
