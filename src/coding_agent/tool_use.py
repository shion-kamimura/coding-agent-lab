"""addツールを1回実行し、公式SDKで結果を返す学習用実行例。"""

import os
import sys

import anthropic
from anthropic.types import Message, MessageParam, ToolParam

ADD_TOOL: ToolParam = {
    "name": "add",
    "description": "Add two integers and return their sum.",
    "input_schema": {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
        "additionalProperties": False,
    },
}


def add(a: int, b: int) -> int:
    return a + b


def show_metadata(response: Message) -> None:
    print(f"model: {response.model}", file=sys.stderr)
    print(f"stop_reason: {response.stop_reason}", file=sys.stderr)
    print(f"usage: {response.usage}", file=sys.stderr)


def main() -> None:
    model = os.environ.get("LLM_MODEL", "claude-haiku-5-5").strip()
    if not model:
        raise SystemExit("LLM_MODEL must not be empty.")
    messages: list[MessageParam] = [{"role": "user", "content": "17と25を足して"}]
    try:
        with anthropic.Anthropic(timeout=30.0, max_retries=2) as client:
            response = client.messages.create(
                model=model,
                max_tokens=16_000,
                thinking={"type": "disabled"},
                messages=messages,
                tools=[ADD_TOOL],
                tool_choice={
                    "type": "tool",
                    "name": "add",
                    "disable_parallel_tool_use": True,
                },
                stream=False,
            )
            show_metadata(response)
            calls = [block for block in response.content if block.type == "tool_use"]
            if response.stop_reason != "tool_use" or len(calls) != 1:
                raise SystemExit("Expected exactly one tool call with tool_use stop.")
            call = calls[0]
            if call.name != "add":
                raise SystemExit("Unknown tool name.")
            arguments = call.input
            if (
                not isinstance(arguments, dict)
                or set(arguments) != {"a", "b"}
                or type(arguments["a"]) is not int
                or type(arguments["b"]) is not int
            ):
                raise SystemExit("add requires exactly two integer arguments.")
            result = add(arguments["a"], arguments["b"])
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": str(result),
                        }
                    ],
                }
            )
            final = client.messages.create(
                model=model,
                max_tokens=16_000,
                thinking={"type": "disabled"},
                messages=messages,
                tools=[ADD_TOOL],
                tool_choice={"type": "none"},
                stream=False,
            )
    except anthropic.AnthropicError as error:
        raise SystemExit(f"Claude SDK error ({type(error).__name__}).") from None

    show_metadata(final)
    if final.stop_reason != "end_turn" or any(
        block.type == "tool_use" for block in final.content
    ):
        raise SystemExit("Claude response did not finish normally.")
    text = "".join(block.text for block in final.content if block.type == "text")
    if not text.strip():
        raise SystemExit("Claude response contained no text.")
    print(text)


if __name__ == "__main__":
    main()
