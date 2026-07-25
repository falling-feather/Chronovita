import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import BaseModel, ConfigDict, Field


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from settings import settings
from services.llm import (
    LLMFailureCode,
    StructuredLLMAdapter,
    StructuredLLMError,
    stream_chat,
)


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str = Field(min_length=2)
    confidence: float = Field(ge=0, le=1)


class PermissiveOutput(BaseModel):
    action_id: str


class PermissiveNestedOutput(BaseModel):
    value: int


class NestedEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nested: PermissiveNestedOutput


class SlowByteStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        for _ in range(10):
            await asyncio.sleep(0.2)
            yield b" "

    async def aclose(self) -> None:
        return None


class StructuredLLMAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_json_is_strictly_parsed_and_checksummed(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {"action_id": "survey", "confidence": 0.94}
                                )
                            },
                        }
                    ]
                },
            )

        adapter = self._adapter(httpx.MockTransport(handler))
        result = await adapter.complete(
            [{"role": "user", "content": "勘察河道"}],
            ExampleOutput,
        )

        self.assertEqual(result.output.action_id, "survey")
        self.assertEqual(result.output.confidence, 0.94)
        self.assertRegex(result.info.output_checksum, r"^[0-9a-f]{64}$")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertFalse(captured["stream"])
        self.assertIn("JSON Schema", captured["messages"][0]["content"])
        self.assertEqual(captured["thinking"], {"type": "disabled"})

    async def test_unknown_fields_are_rejected_by_output_schema(self):
        adapter = self._json_adapter(
            {"action_id": "survey", "confidence": 0.8, "state": {"risk": 0}}
        )
        with self.assertRaises(StructuredLLMError) as caught:
            await adapter.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(caught.exception.code, LLMFailureCode.OUTPUT_VALIDATION_FAILED)

        string_number = self._json_adapter(
            {"action_id": "survey", "confidence": "0.8"}
        )
        with self.assertRaises(StructuredLLMError) as strict_error:
            await string_number.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(
            strict_error.exception.code,
            LLMFailureCode.OUTPUT_VALIDATION_FAILED,
        )

    async def test_duplicate_keys_and_truncated_outputs_are_rejected(self):
        duplicate = self._content_adapter(
            '{"action_id":"survey","action_id":"dam","confidence":0.9}'
        )
        with self.assertRaises(StructuredLLMError) as duplicate_error:
            await duplicate.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(duplicate_error.exception.code, LLMFailureCode.INVALID_RESPONSE)

        truncated = self._content_adapter(
            '{"action_id":"survey"',
            finish_reason="length",
        )
        with self.assertRaises(StructuredLLMError) as truncated_error:
            await truncated.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(truncated_error.exception.code, LLMFailureCode.RESPONSE_TRUNCATED)
        self.assertTrue(truncated_error.exception.retryable)

    async def test_timeout_rate_limit_and_provider_body_do_not_leak(self):
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout(
                "upstream leaked-token-123",
                request=request,
            )

        with self.assertRaises(StructuredLLMError) as timeout_error:
            await self._adapter(httpx.MockTransport(timeout_handler)).complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(timeout_error.exception.code, LLMFailureCode.PROVIDER_TIMEOUT)
        self.assertNotIn("leaked-token", str(timeout_error.exception))

        def rate_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="secret-provider-body")

        with self.assertRaises(StructuredLLMError) as rate_error:
            await self._adapter(httpx.MockTransport(rate_handler)).complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(rate_error.exception.code, LLMFailureCode.PROVIDER_RATE_LIMITED)
        self.assertNotIn("secret-provider-body", str(rate_error.exception))

        def unavailable_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="private-maintenance-detail")

        with self.assertRaises(StructuredLLMError) as unavailable_error:
            await self._adapter(httpx.MockTransport(unavailable_handler)).complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(
            unavailable_error.exception.code,
            LLMFailureCode.PROVIDER_UNAVAILABLE,
        )
        self.assertNotIn("private-maintenance-detail", str(unavailable_error.exception))

    async def test_response_size_and_unconfigured_provider_fail_closed(self):
        oversized = self._content_adapter(
            json.dumps({"action_id": "x" * 2000, "confidence": 0.8}),
            max_response_bytes=1024,
        )
        with self.assertRaises(StructuredLLMError) as size_error:
            await oversized.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(size_error.exception.code, LLMFailureCode.RESPONSE_TOO_LARGE)

        unconfigured = StructuredLLMAdapter(provider="mock", api_key="")
        with self.assertRaises(StructuredLLMError) as provider_error:
            await unconfigured.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(
            provider_error.exception.code,
            LLMFailureCode.PROVIDER_UNCONFIGURED,
        )

    async def test_empty_malformed_and_non_object_outputs_fail_closed(self):
        for content in ("", "not json", "[]", '{"confidence":NaN}'):
            with self.subTest(content=content):
                adapter = self._content_adapter(content)
                with self.assertRaises(StructuredLLMError) as caught:
                    await adapter.complete(
                        [{"role": "user", "content": "survey"}],
                        ExampleOutput,
                    )
                self.assertEqual(caught.exception.code, LLMFailureCode.INVALID_RESPONSE)

        malformed_envelopes = (
            [],
            {"choices": []},
            {"choices": ["not-an-object"]},
            {"choices": [{"finish_reason": [], "message": {"content": "{}"}}]},
            {"choices": [{"finish_reason": "stop", "message": []}]},
        )
        for envelope in malformed_envelopes:
            with self.subTest(envelope=envelope):
                adapter = self._envelope_adapter(envelope)
                with self.assertRaises(StructuredLLMError) as caught:
                    await adapter.complete(
                        [{"role": "user", "content": "survey"}],
                        ExampleOutput,
                    )
                self.assertEqual(caught.exception.code, LLMFailureCode.INVALID_RESPONSE)

    async def test_timeout_is_a_total_deadline_not_only_a_read_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=SlowByteStream())

        with self.assertRaises(StructuredLLMError) as caught:
            await self._adapter(httpx.MockTransport(handler)).complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(caught.exception.code, LLMFailureCode.PROVIDER_TIMEOUT)

    async def test_invalid_message_and_adapter_limits_are_stable(self):
        adapter = self._adapter(httpx.MockTransport(lambda request: httpx.Response(200)))
        with self.assertRaises(StructuredLLMError) as message_error:
            await adapter.complete(
                [{"role": "tool", "content": "not allowed"}],
                ExampleOutput,
            )
        self.assertEqual(message_error.exception.code, LLMFailureCode.INVALID_REQUEST)

        invalid_limits = StructuredLLMAdapter(
            provider="deepseek",
            api_key="adapter-test-key",
            base_url="file:///private/provider",
            timeout_seconds=0,
            max_response_bytes=12,
            default_max_tokens=5000,
        )
        with self.assertRaises(StructuredLLMError) as limit_error:
            await invalid_limits.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
            )
        self.assertEqual(limit_error.exception.code, LLMFailureCode.INVALID_REQUEST)

        with self.assertRaises(StructuredLLMError) as token_error:
            await adapter.complete(
                [{"role": "user", "content": "survey"}],
                ExampleOutput,
                max_tokens=0,
            )
        self.assertEqual(token_error.exception.code, LLMFailureCode.INVALID_REQUEST)

        with self.assertRaises(StructuredLLMError) as schema_error:
            await adapter.complete(
                [{"role": "user", "content": "survey"}],
                PermissiveOutput,
            )
        self.assertEqual(schema_error.exception.code, LLMFailureCode.INVALID_REQUEST)

        with self.assertRaises(StructuredLLMError) as nested_schema_error:
            await adapter.complete(
                [{"role": "user", "content": "survey"}],
                NestedEnvelope,
            )
        self.assertEqual(
            nested_schema_error.exception.code,
            LLMFailureCode.INVALID_REQUEST,
        )

    async def test_legacy_stream_http_error_uses_stable_mock_fallback(self):
        previous = {
            "deepseek_api_key": settings.deepseek_api_key,
            "deepseek_base_url": settings.deepseek_base_url,
        }
        settings.deepseek_api_key = "stream-test-key"
        settings.deepseek_base_url = "https://provider.test"
        real_client = httpx.AsyncClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="private-upstream-debug-body")

        transport = httpx.MockTransport(handler)

        def client_factory(**kwargs):
            return real_client(
                timeout=kwargs.get("timeout"),
                transport=transport,
            )

        try:
            with patch("services.llm.httpx.AsyncClient", side_effect=client_factory):
                output = "".join(
                    [
                        chunk
                        async for chunk in stream_chat(
                            [{"role": "user", "content": "测试问题"}],
                            provider="deepseek",
                        )
                    ]
                )
        finally:
            for key, value in previous.items():
                setattr(settings, key, value)

        self.assertIn("模型服务暂不可用", output)
        self.assertIn("离线 mock 回答", output)
        self.assertNotIn("private-upstream-debug-body", output)
        self.assertNotIn("500", output)

    def _adapter(
        self,
        transport: httpx.AsyncBaseTransport,
        *,
        max_response_bytes: int = 32 * 1024,
    ) -> StructuredLLMAdapter:
        return StructuredLLMAdapter(
            provider="deepseek",
            api_key="adapter-test-key",
            base_url="https://provider.test",
            default_model="deepseek-v4-flash",
            timeout_seconds=1,
            max_response_bytes=max_response_bytes,
            default_max_tokens=128,
            transport=transport,
        )

    def _json_adapter(self, payload: dict) -> StructuredLLMAdapter:
        return self._content_adapter(json.dumps(payload))

    def _content_adapter(
        self,
        content: str,
        *,
        finish_reason: str = "stop",
        max_response_bytes: int = 32 * 1024,
    ) -> StructuredLLMAdapter:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": finish_reason,
                            "message": {"content": content},
                        }
                    ]
                },
            )

        return self._adapter(
            httpx.MockTransport(handler),
            max_response_bytes=max_response_bytes,
        )

    def _envelope_adapter(self, envelope) -> StructuredLLMAdapter:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=envelope)

        return self._adapter(httpx.MockTransport(handler))


if __name__ == "__main__":
    unittest.main()
