"""Agent SDKで、一時的な算術課題を編集して固定テストを確認する学習例。"""

import asyncio
import json
import os
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

from coding_agent.repair_exercise import BROKEN as BROKEN
from coding_agent.repair_exercise import SYSTEM, TASK
from coding_agent.repair_exercise import TESTS as TESTS
from coding_agent.repair_exercise import Exercise as SharedExercise
from coding_agent.repair_exercise import check_source as check_source

TEST_TOOL = "mcp__checks__run_tests"


class Exercise(SharedExercise):
    """Agent SDKのツール名・hook・終了状態を共有課題へ接続する。"""

    def permits(self, name: str, arguments: dict[str, Any]) -> bool:
        if name not in {"Read", "Edit", TEST_TOOL}:
            return False
        return super().permits("run_tests" if name == TEST_TOOL else name, arguments)

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
        if result is None or result.is_error or result.subtype != "success":
            raise ValueError("Repair incomplete: no verified model test result.")
        return self.checked_diff()


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
            system_prompt=SYSTEM,
        )
        final: ResultMessage | None = None
        async with asyncio.timeout(120), ClaudeSDKClient(options=options) as client:
            await client.query(TASK)
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
