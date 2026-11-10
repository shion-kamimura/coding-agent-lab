"""単一addツールを逐次実行する、上限付きの学習用Agent Loop。"""

import os
import sys

import anthropic
from anthropic.types import MessageParam

from coding_agent import tool_use


def main(*, max_steps: int = 5) -> None:
    # boolはintの派生型だが、ステップ数としては受け付けない。
    if type(max_steps) is not int or max_steps <= 0:
        raise SystemExit("max_steps must be a positive integer.")
    model = os.environ.get("LLM_MODEL", "claude-haiku-5-5").strip()
    if not model:
        raise SystemExit("LLM_MODEL must not be empty.")
    messages: list[MessageParam] = [
        {"role": "user", "content": "17と25を足し、その結果に8を足して"}
    ]
    try:
        with anthropic.Anthropic(timeout=30.0, max_retries=2) as client:
            for step in range(1, max_steps + 1):
                response = client.messages.create(
                    model=model,
                    max_tokens=16_000,
                    thinking={"type": "disabled"},
                    messages=messages,
                    tools=[tool_use.ADD_TOOL],
                    tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                    stream=False,
                )
                print(f"step: {step}/{max_steps}", file=sys.stderr)
                tool_use.show_metadata(response)
                calls = [b for b in response.content if b.type == "tool_use"]
                if response.stop_reason == "end_turn" and not calls:
                    text = "".join(b.text for b in response.content if b.type == "text")
                    if not text.strip():
                        raise SystemExit("Claude response contained no text.")
                    print(text)
                    return
                if response.stop_reason != "tool_use" or len(calls) != 1:
                    raise SystemExit("Expected one tool call or a normal final answer.")
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
                try:
                    result = tool_use.add(arguments["a"], arguments["b"])
                except Exception:
                    # ツールの例外本文・入力をログにもモデルにも渡さない。
                    raise SystemExit("add execution failed.") from None
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
    except anthropic.AnthropicError as error:
        raise SystemExit(f"Claude SDK error ({type(error).__name__}).") from None
    raise SystemExit("Agent Loop incomplete: max_steps reached without a final answer.")


if __name__ == "__main__":
    main()
