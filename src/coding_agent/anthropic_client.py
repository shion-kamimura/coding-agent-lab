"""Claude Messages APIと内部の同期テキスト生成インターフェースの変換。"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Literal

import anthropic
from anthropic.types import Message as APIMessage
from anthropic.types import MessageParam, Usage

from coding_agent.llm import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMRequestError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
    LLMTruncatedResponseError,
    Message,
    TokenUsage,
)

DEFAULT_MODEL = "claude-haiku-5-5"
SONNET_MODEL = "claude-sonnet-5-5"
type Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class AnthropicConfig:
    model: str = DEFAULT_MODEL
    max_output_tokens: int = 16_000
    timeout_seconds: float = 30.0
    max_retries: int = 2
    effort: Effort = "medium"

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Model must not be empty.")
        if type(self.max_output_tokens) is not int or self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive.")
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer.")
        if self.effort not in ("low", "medium", "high", "xhigh", "max"):
            raise ValueError("Unsupported effort level.")


class AnthropicClient:
    """SDKの生成と終了は呼び出し元が担当し、再試行はSDKだけで行う。"""

    def __init__(
        self,
        client: anthropic.Anthropic,
        *,
        config: AnthropicConfig | None = None,
    ) -> None:
        self._config = config if config is not None else AnthropicConfig()
        self._client = client.with_options(
            timeout=self._config.timeout_seconds, max_retries=self._config.max_retries
        )

    def complete(self, messages: Sequence[Message]) -> LLMResponse:
        conversation = [message for message in messages if message.role != "system"]
        if not conversation:
            raise ValueError("At least one user message is required.")
        if conversation[0].role != "user" or conversation[-1].role != "user":
            raise ValueError("Conversation must start and end with a user message.")
        inputs: list[MessageParam] = []
        for message in messages:
            if message.role == "system":
                inputs.append({"role": "system", "content": message.content})
            elif message.role == "assistant":
                inputs.append({"role": "assistant", "content": message.content})
            else:
                inputs.append({"role": "user", "content": message.content})
        try:
            response = self._client.messages.create(
                model=self._config.model.strip(),
                messages=inputs,
                max_tokens=self._config.max_output_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": self._config.effort},
                stream=False,
            )
        except anthropic.AuthenticationError, anthropic.PermissionDeniedError:
            raise LLMAuthenticationError(
                "LLM authentication or access denied."
            ) from None
        except anthropic.RateLimitError:
            raise LLMRateLimitError("LLM rate or quota limit reached.") from None
        except anthropic.APITimeoutError:
            raise LLMTimeoutError("LLM request timed out.") from None
        except anthropic.APIConnectionError:
            raise LLMConnectionError("LLM connection failed.") from None
        except anthropic.APIResponseValidationError:
            raise LLMResponseError("LLM returned an invalid response.") from None
        except anthropic.APIError:
            raise LLMRequestError("LLM request failed.") from None
        except JSONDecodeError:
            raise LLMResponseError("LLM returned an invalid response.") from None
        return _convert_response(response)


def _convert_usage(usage: Usage | None) -> TokenUsage | None:
    if usage is None:
        return None
    try:
        details = usage.output_tokens_details
        return TokenUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_input_tokens=(
                usage.cache_creation_input_tokens
                if usage.cache_creation_input_tokens is not None
                else 0
            ),
            cache_read_input_tokens=(
                usage.cache_read_input_tokens
                if usage.cache_read_input_tokens is not None
                else 0
            ),
            thinking_tokens=details.thinking_tokens if details is not None else None,
        )
    except AttributeError, TypeError, ValueError:
        raise LLMResponseError("LLM returned invalid token usage.") from None


def _convert_response(response: APIMessage) -> LLMResponse:
    if (
        getattr(response, "type", None) != "message"
        or getattr(response, "role", None) != "assistant"
    ):
        raise LLMResponseError("LLM returned an invalid message.")
    model = getattr(response, "model", None)
    if not isinstance(model, str) or not model.strip():
        raise LLMResponseError("LLM response contained no model name.")
    usage = _convert_usage(getattr(response, "usage", None))
    stop_reason = response.stop_reason
    if stop_reason in ("max_tokens", "model_context_window_exceeded"):
        raise LLMTruncatedResponseError(
            "LLM response was truncated.",
            model=model,
            stop_reason=stop_reason,
            usage=usage,
        )
    if stop_reason == "refusal":
        raise LLMRefusalError(
            "LLM refused the request.",
            model=model,
            stop_reason=stop_reason,
            usage=usage,
        )
    if stop_reason != "end_turn":
        raise LLMResponseError(
            "LLM response did not finish normally.", model=model, usage=usage
        )
    content = getattr(response, "content", None)
    if not isinstance(content, list):
        raise LLMResponseError(
            "LLM returned invalid content.", model=model, usage=usage
        )
    parts: list[str] = []
    for block in content:
        kind = getattr(block, "type", None)
        if kind == "text":
            text = getattr(block, "text", None)
            if not isinstance(text, str):
                raise LLMResponseError("LLM returned invalid text.")
            parts.append(text)
        elif kind not in ("thinking", "redacted_thinking"):
            raise LLMResponseError("LLM returned unsupported content.")
    text = "".join(parts)
    if not text.strip():
        raise LLMResponseError(
            "LLM response contained no text.",
            model=model,
            stop_reason=stop_reason,
            usage=usage,
        )
    return LLMResponse(text=text, model=model, usage=usage)
