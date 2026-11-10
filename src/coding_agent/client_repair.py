"""公式Client SDKで同じ算術課題を修正する手動ループ。"""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import anthropic
from anthropic.types import MessageParam, ToolParam

from coding_agent.repair_exercise import SYSTEM, TASK, Exercise

TOOLS: list[ToolParam] = [
    {
        "name": "Read",
        "description": "Read one of the two exercise files as UTF-8 text.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "Edit",
        "description": "Replace one unique substring in calculator.py.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["file_path", "old_string", "new_string"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_tests",
        "description": "Run the fixed addition tests; no arguments.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def execute(exercise: Exercise, name: str, arguments: object) -> dict[str, object]:
    """操作拒否とテスト失敗は次の要求へ返す。想定外の例外は呼出側で停止する。"""
    if not isinstance(arguments, dict):
        return {"error": "Operation denied."}
    try:
        if not exercise.permits(name, arguments):
            return {"error": "Operation denied."}
        if name == "run_tests":
            exercise.test_runs += 1
            try:
                return exercise.run_tests()
            except Exception:
                return {"error": "Tests could not run."}
        path = Path(arguments["file_path"])
        if not path.is_absolute():
            path = exercise.root / path
        if name == "Read":
            if set(arguments) != {"file_path"}:
                return {"error": "Operation denied."}
            return {"text": path.read_text(encoding="utf-8")}
        old, new = arguments["old_string"], arguments["new_string"]
        path.write_text(exercise.source().replace(old, new, 1), encoding="utf-8")
        return {"edited": "calculator.py"}
    except ValueError:
        return {"error": "Operation denied."}


def repair(*, max_steps: int = 12) -> str:
    """API要求・ツール実行・履歴更新・停止を明示する。製品CLIではない。"""
    if type(max_steps) is not int or not 1 <= max_steps <= 20:
        raise ValueError("max_steps must be an integer between 1 and 20.")
    model = os.environ.get("LLM_MODEL", "claude-haiku-5-5").strip()
    if not model:
        raise ValueError("LLM_MODEL must not be empty.")
    with TemporaryDirectory(prefix="coding-agent-client-exercise-") as directory:
        exercise = Exercise(Path(directory) / "project")
        if exercise.run_tests()["returncode"] == 0:
            raise ValueError("Repair incomplete: baseline unexpectedly passed.")
        messages: list[MessageParam] = [{"role": "user", "content": TASK}]
        with anthropic.Anthropic(timeout=30.0, max_retries=0) as client:
            for _ in range(max_steps):
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    thinking={"type": "disabled"},
                    system=SYSTEM,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                    stream=False,
                )
                calls = [b for b in response.content if b.type == "tool_use"]
                if response.stop_reason == "end_turn" and not calls:
                    if not any(
                        b.type == "text" and b.text.strip() for b in response.content
                    ):
                        raise ValueError("Repair incomplete: empty final response.")
                    diff = exercise.checked_diff()
                    return (
                        "修正前: 固定テスト失敗\n"
                        "修正後: 固定テスト4件成功（アプリで再実行済み）\n"
                        f"モデルからのテスト実行: {exercise.test_runs}回\n{diff}"
                    )
                if response.stop_reason != "tool_use" or len(calls) != 1:
                    raise ValueError("Repair incomplete: unexpected response.")
                call = calls[0]
                result = execute(exercise, call.name, call.input)
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": call.id,
                                "content": json.dumps(result, ensure_ascii=False),
                                "is_error": "error" in result,
                            }
                        ],
                    }
                )
    raise ValueError("Repair incomplete: max_steps reached.")


def main() -> None:
    try:
        print(repair())
    except Exception:
        raise SystemExit(
            "Repair stopped: SDK, test, or verification failure."
        ) from None


if __name__ == "__main__":
    main()
