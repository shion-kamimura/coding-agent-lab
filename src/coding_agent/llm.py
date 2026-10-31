"""プロバイダーに依存しない、同期テキスト生成の境界。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("system", "user", "assistant"):
            raise ValueError("Unsupported message role.")
        if not self.content.strip():
            raise ValueError("Message content must not be empty.")


@dataclass(frozen=True)
class TokenUsage:
    """入力は未キャッシュ分。出力は推論を含む課金対象の合計。"""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    thinking_tokens: int | None = None

    def __post_init__(self) -> None:
        counts = (
            self.input_tokens,
            self.output_tokens,
            self.cache_creation_input_tokens,
            self.cache_read_input_tokens,
        )
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("Token counts must be non-negative integers.")
        if self.thinking_tokens is not None and (
            type(self.thinking_tokens) is not int
            or not 0 <= self.thinking_tokens <= self.output_tokens
        ):
            raise ValueError("Thinking tokens must be within total output tokens.")

    @property
    def total_input_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    usage: TokenUsage | None


class LLMClient(Protocol):
    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        """完成したテキストを返す。API失敗はLLMError、不正な入力はValueError。"""
        ...


class LLMError(Exception):
    """SDK固有の例外やレスポンス本文を外部へ公開しない基底例外。"""


class LLMAuthenticationError(LLMError):
    """認証またはアクセス権限の問題。"""


class LLMRateLimitError(LLMError):
    """再試行後もレート制限またはクォータ制限に達した。"""


class LLMConnectionError(LLMError):
    """再試行後も通信に失敗した。"""


class LLMTimeoutError(LLMConnectionError):
    """通信がタイムアウトした。"""


class LLMRequestError(LLMError):
    """APIリクエストが失敗した。"""


class LLMResponseError(LLMError):
    """応答が未完了、拒否、または利用できない形式だった。"""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        stop_reason: str | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.stop_reason = stop_reason
        self.usage = usage


class LLMTruncatedResponseError(LLMResponseError):
    """出力上限またはコンテキスト上限で応答が打ち切られた。"""


class LLMRefusalError(LLMResponseError):
    """モデルが要求への応答を拒否した。"""
