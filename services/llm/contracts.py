from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=16_000)


class LLMFailureCode(str, Enum):
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    PROVIDER_UNCONFIGURED = "provider_unconfigured"
    INVALID_REQUEST = "invalid_request"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_REJECTED = "provider_rejected"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RESPONSE_TOO_LARGE = "response_too_large"
    RESPONSE_TRUNCATED = "response_truncated"
    INVALID_RESPONSE = "invalid_response"
    OUTPUT_VALIDATION_FAILED = "output_validation_failed"


class StructuredLLMError(RuntimeError):
    def __init__(
        self,
        code: LLMFailureCode,
        *,
        provider: str,
        retryable: bool,
    ) -> None:
        self.code = code
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"structured LLM request failed: {code.value}")


class StructuredCompletionInfo(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    finish_reason: str | None = Field(default=None, max_length=64)
    output_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True)
class StructuredCompletion(Generic[OutputT]):
    output: OutputT
    info: StructuredCompletionInfo
