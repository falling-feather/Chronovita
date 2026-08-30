import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.ai import ScenarioDialogueLLMAdapterV1
from services.game_runtime.dialogue_models import (
    ScenarioDialogueExternalCompletionV1,
    ScenarioDialogueModelOutputV1,
)
from services.llm import (
    LLMFailureCode,
    StructuredCompletion,
    StructuredCompletionInfo,
    StructuredLLMError,
)

MESSAGES = [
    {
        "role": "system",
        "content": "只能润色已经结算的本地台词，并引用允许的证据片段。",
    },
    {
        "role": "user",
        "content": '{"local_text":"先察水势。","allowed_passages":["passage-a"]}',
    },
]


class FakeCompleter:
    def __init__(self, *, output=None, info=None, error=None):
        self.output = output
        self.info = info or StructuredCompletionInfo(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="stop",
            output_checksum="a" * 64,
        )
        self.error = error
        self.calls = []

    async def complete(
        self,
        messages,
        response_model,
        *,
        model=None,
        temperature=0.0,
        max_tokens=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "response_model": response_model,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if self.error is not None:
            raise self.error
        return StructuredCompletion(output=self.output, info=self.info)


class GameDialogueAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_wraps_only_output_and_server_provider_provenance(self):
        output = ScenarioDialogueModelOutputV1(
            text="先察明支流水势，再决定如何分导。",
            used_passage_ids=("passage-a",),
        )
        completer = FakeCompleter(output=output)
        adapter = ScenarioDialogueLLMAdapterV1(
            completer=completer,
            model="dialogue-test-model",
        )

        result = await adapter(MESSAGES)

        self.assertIsInstance(result, ScenarioDialogueExternalCompletionV1)
        self.assertEqual(result.output, output)
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.model, "deepseek-v4-flash")
        self.assertEqual(
            set(result.output.model_dump(mode="python")),
            {"text", "used_passage_ids"},
        )
        self.assertEqual(len(completer.calls), 1)
        call = completer.calls[0]
        self.assertEqual(call["messages"], MESSAGES)
        self.assertIs(call["response_model"], ScenarioDialogueModelOutputV1)
        self.assertEqual(call["model"], "dialogue-test-model")
        self.assertEqual(call["temperature"], 0.2)
        self.assertEqual(call["max_tokens"], 320)

    async def test_illegal_model_output_validation_error_bubbles_to_projection(self):
        illegal_outputs = (
            {
                "text": "试图越权改变结局。",
                "used_passage_ids": ("passage-a",),
                "ending_id": "invented-ending",
            },
            {
                "text": "引用顺序不稳定。",
                "used_passage_ids": ("passage-b", "passage-a"),
            },
            {
                "text": "没有引用。",
                "used_passage_ids": (),
            },
        )
        for output in illegal_outputs:
            with self.subTest(output=output):
                adapter = ScenarioDialogueLLMAdapterV1(
                    completer=FakeCompleter(output=output)
                )
                with self.assertRaises(ValidationError):
                    await adapter.generate(MESSAGES)

    async def test_invalid_completion_info_validation_error_bubbles(self):
        output = ScenarioDialogueModelOutputV1(
            text="先察水势。",
            used_passage_ids=("passage-a",),
        )
        invalid_info = StructuredCompletionInfo.model_construct(
            provider="",
            model="",
            finish_reason="stop",
            output_checksum="not-a-checksum",
        )
        adapter = ScenarioDialogueLLMAdapterV1(
            completer=FakeCompleter(output=output, info=invalid_info)
        )

        with self.assertRaises(ValidationError):
            await adapter(MESSAGES)

    async def test_structured_provider_failure_is_not_swallowed(self):
        failure = StructuredLLMError(
            LLMFailureCode.PROVIDER_TIMEOUT,
            provider="deepseek",
            retryable=True,
        )
        completer = FakeCompleter(error=failure)
        adapter = ScenarioDialogueLLMAdapterV1(completer=completer)

        with self.assertRaises(StructuredLLMError) as raised:
            await adapter(MESSAGES)

        self.assertIs(raised.exception, failure)
        self.assertEqual(len(completer.calls), 1)


if __name__ == "__main__":
    unittest.main()
