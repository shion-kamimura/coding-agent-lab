"""公式SDKで1回のテキスト生成を行う学習用実行例。"""

import os
import sys

import anthropic


def main() -> None:
    model = os.environ.get("LLM_MODEL", "claude-haiku-5-5").strip()
    if not model:
        raise SystemExit("LLM_MODEL must not be empty.")

    try:
        with anthropic.Anthropic(timeout=30.0, max_retries=2) as client:
            response = client.messages.create(
                model=model,
                max_tokens=16_000,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                messages=[
                    {"role": "user", "content": "PythonのProtocolを短く説明して"}
                ],
                stream=False,
            )
    except anthropic.AnthropicError as error:
        # SDK例外の本文には入力や応答が含まれる可能性があるため表示しない。
        raise SystemExit(f"Claude SDK error ({type(error).__name__}).") from None

    print(f"model: {response.model}", file=sys.stderr)
    print(f"stop_reason: {response.stop_reason}", file=sys.stderr)
    print(f"usage: {response.usage}", file=sys.stderr)
    if response.stop_reason != "end_turn":
        raise SystemExit("Claude response did not finish normally.")

    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise SystemExit("Claude response contained no text.")
    print(text)


if __name__ == "__main__":
    main()
