"""プロバイダーに依存しない入力と使用量の契約を検証する。"""

from typing import Literal, cast

import pytest

from coding_agent.llm import Message, TokenUsage


@pytest.mark.parametrize("content", ["", " \n "])
def test_empty_message_is_rejected(content: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Message("user", content)


def test_unknown_message_role_is_rejected() -> None:
    role = cast(Literal["user"], "tool")
    with pytest.raises(ValueError, match="Unsupported message role"):
        Message(role, "result")


def test_usage_keeps_cache_categories_and_counts_thinking_once() -> None:
    usage = TokenUsage(
        input_tokens=10,
        output_tokens=30,
        cache_creation_input_tokens=5,
        cache_read_input_tokens=7,
        thinking_tokens=20,
    )

    assert usage.total_input_tokens == 22
    assert usage.output_tokens == 30
    assert usage.thinking_tokens == 20


@pytest.mark.parametrize("thinking_tokens", [-1, 31])
def test_invalid_thinking_usage_is_rejected(thinking_tokens: int) -> None:
    with pytest.raises(ValueError, match="within total output"):
        TokenUsage(10, 30, thinking_tokens=thinking_tokens)


def test_negative_usage_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TokenUsage(-1, 30)
