from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Iterable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from settings import settings

from .contracts import (
    LLMFailureCode,
    LLMMessage,
    StructuredCompletion,
    StructuredCompletionInfo,
    StructuredLLMError,
)


OutputT = TypeVar("OutputT", bound=BaseModel)

_JSON_INSTRUCTION = (
    "Return exactly one valid JSON object matching the supplied JSON Schema. "
    "Do not return markdown, prose, code fences, or additional keys."
)
_MAX_PROMPT_BYTES = 64 * 1024


class StructuredLLMAdapter:
    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout_seconds: float | None = None,
        max_response_bytes: int | None = None,
        default_max_tokens: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider = (provider or settings.llm_provider or "mock").strip().lower()
        self.api_key = (
            settings.deepseek_api_key if api_key is None else api_key
        ).strip()
        self.base_url = (
            base_url or settings.deepseek_base_url
        ).strip().rstrip("/")
        self.default_model = (
            default_model or settings.deepseek_model
        ).strip()
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.llm_structured_timeout_seconds
        )
        self.max_response_bytes = (
            max_response_bytes
            if max_response_bytes is not None
            else settings.llm_structured_max_response_bytes
        )
        self.default_max_tokens = (
            default_max_tokens
            if default_max_tokens is not None
            else settings.llm_structured_max_tokens
        )
        self.transport = transport

    async def complete(
        self,
        messages: Iterable[LLMMessage | dict[str, Any]],
        response_model: type[OutputT],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> StructuredCompletion[OutputT]:
        provider = self.provider
        if provider not in {"mock", "deepseek"}:
            raise self._error(LLMFailureCode.UNSUPPORTED_PROVIDER, retryable=False)
        if provider == "mock" or not self.api_key:
            raise self._error(LLMFailureCode.PROVIDER_UNCONFIGURED, retryable=False)

        try:
            use_model = (
                self.default_model if model is None else model
            ).strip()
            token_limit = (
                self.default_max_tokens if max_tokens is None else max_tokens
            )
            base_url = httpx.URL(self.base_url)
        except (AttributeError, TypeError, ValueError):
            raise self._error(LLMFailureCode.INVALID_REQUEST, retryable=False) from None
        if (
            not use_model
            or len(use_model) > 128
            or isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not 0 <= temperature <= 2
            or isinstance(token_limit, bool)
            or not isinstance(token_limit, int)
            or not 1 <= token_limit <= 4096
            or isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 1 <= self.timeout_seconds <= 60
            or isinstance(self.max_response_bytes, bool)
            or not isinstance(self.max_response_bytes, int)
            or not 1024 <= self.max_response_bytes <= 256 * 1024
            or base_url.scheme != "https"
            or not base_url.host
            or response_model.model_config.get("extra") != "forbid"
        ):
            raise self._error(LLMFailureCode.INVALID_REQUEST, retryable=False)

        request_messages = self._prepare_messages(messages, response_model)
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": request_messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": token_limit,
            "response_format": {"type": "json_object"},
        }
        if use_model.startswith("deepseek-v4"):
            payload["thinking"] = {"type": "disabled"}

        response = await self._post(payload)
        raw_output, finish_reason = self._extract_output(response)
        output = self._validate_output(raw_output, response_model)
        canonical = json.dumps(
            output.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        return StructuredCompletion(
            output=output,
            info=StructuredCompletionInfo(
                provider=provider,
                model=use_model,
                finish_reason=finish_reason,
                output_checksum=hashlib.sha256(canonical).hexdigest(),
            ),
        )

    def _prepare_messages(
        self,
        messages: Iterable[LLMMessage | dict[str, Any]],
        response_model: type[BaseModel],
    ) -> list[dict[str, str]]:
        try:
            normalized = [
                item
                if isinstance(item, LLMMessage)
                else LLMMessage.model_validate(item, strict=True)
                for item in messages
            ]
            schema_document = response_model.model_json_schema()
            if not _has_only_closed_object_schemas(schema_document):
                raise ValueError("response schema contains an open object")
            schema = json.dumps(
                schema_document,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError, ValidationError):
            raise self._error(LLMFailureCode.INVALID_REQUEST, retryable=False) from None
        if not normalized:
            raise self._error(LLMFailureCode.INVALID_REQUEST, retryable=False)

        prepared = [
            {
                "role": "system",
                "content": f"{_JSON_INSTRUCTION}\nJSON Schema: {schema}",
            },
            *(item.model_dump(mode="json") for item in normalized),
        ]
        encoded_size = len(
            json.dumps(
                prepared,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        if encoded_size > _MAX_PROMPT_BYTES:
            raise self._error(LLMFailureCode.INVALID_REQUEST, retryable=False)
        return prepared

    async def _post(self, payload: dict[str, Any]) -> bytes:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout_seconds),
                    transport=self.transport,
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        self._check_status(response.status_code)
                        content_length = response.headers.get("content-length")
                        if content_length is not None:
                            try:
                                declared_length = int(content_length)
                                if declared_length < 0:
                                    raise ValueError("negative content length")
                                if declared_length > self.max_response_bytes:
                                    raise self._error(
                                        LLMFailureCode.RESPONSE_TOO_LARGE,
                                        retryable=False,
                                    )
                            except ValueError:
                                raise self._error(
                                    LLMFailureCode.INVALID_RESPONSE,
                                    retryable=False,
                                ) from None
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > self.max_response_bytes:
                                raise self._error(
                                    LLMFailureCode.RESPONSE_TOO_LARGE,
                                    retryable=False,
                                )
                            body.extend(chunk)
        except (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError):
            raise self._error(LLMFailureCode.PROVIDER_TIMEOUT, retryable=True) from None
        except httpx.HTTPError:
            raise self._error(LLMFailureCode.PROVIDER_UNAVAILABLE, retryable=True) from None
        return bytes(body)

    def _check_status(self, status_code: int) -> None:
        if status_code == 429:
            raise self._error(LLMFailureCode.PROVIDER_RATE_LIMITED, retryable=True)
        if status_code in {408, 504}:
            raise self._error(LLMFailureCode.PROVIDER_TIMEOUT, retryable=True)
        if 400 <= status_code < 500:
            raise self._error(LLMFailureCode.PROVIDER_REJECTED, retryable=False)
        if status_code >= 500:
            raise self._error(LLMFailureCode.PROVIDER_UNAVAILABLE, retryable=True)

    def _extract_output(self, response: bytes) -> tuple[str, str | None]:
        try:
            envelope = json.loads(
                response.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_non_finite,
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False) from None
        if not isinstance(envelope, dict):
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False)
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices:
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False)
        choice = choices[0]
        if not isinstance(choice, dict):
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False)
        finish_reason = choice.get("finish_reason")
        message = choice.get("message")
        if not isinstance(finish_reason, str) or not isinstance(message, dict):
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False)
        content = message.get("content")
        if finish_reason == "length":
            raise self._error(LLMFailureCode.RESPONSE_TRUNCATED, retryable=True)
        if finish_reason == "insufficient_system_resource":
            raise self._error(LLMFailureCode.PROVIDER_UNAVAILABLE, retryable=True)
        if finish_reason != "stop":
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False)
        if not isinstance(content, str) or not content.strip():
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False)
        if len(content.encode("utf-8")) > self.max_response_bytes:
            raise self._error(LLMFailureCode.RESPONSE_TOO_LARGE, retryable=False)
        return content, finish_reason

    def _validate_output(
        self,
        raw_output: str,
        response_model: type[OutputT],
    ) -> OutputT:
        try:
            decoded = json.loads(
                raw_output,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_non_finite,
            )
        except (ValueError, json.JSONDecodeError):
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False) from None
        if not isinstance(decoded, dict):
            raise self._error(LLMFailureCode.INVALID_RESPONSE, retryable=False)
        try:
            return response_model.model_validate(decoded, strict=True)
        except ValidationError:
            raise self._error(
                LLMFailureCode.OUTPUT_VALIDATION_FAILED,
                retryable=False,
            ) from None

    def _error(
        self,
        code: LLMFailureCode,
        *,
        retryable: bool,
    ) -> StructuredLLMError:
        return StructuredLLMError(
            code,
            provider=self.provider,
            retryable=retryable,
        )


async def complete_json(
    messages: Iterable[LLMMessage | dict[str, Any]],
    response_model: type[OutputT],
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> StructuredCompletion[OutputT]:
    return await StructuredLLMAdapter(provider=provider).complete(
        messages,
        response_model,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _has_only_closed_object_schemas(value: Any) -> bool:
    if isinstance(value, dict):
        is_object = value.get("type") == "object" or "properties" in value
        if is_object and value.get("additionalProperties") is not False:
            return False
        return all(_has_only_closed_object_schemas(item) for item in value.values())
    if isinstance(value, list):
        return all(_has_only_closed_object_schemas(item) for item in value)
    return True
