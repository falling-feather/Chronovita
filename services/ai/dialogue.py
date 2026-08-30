from __future__ import annotations

from typing import Protocol, Sequence

from pydantic import BaseModel

from services.game_runtime.dialogue_models import (
    ScenarioDialogueExternalCompletionV1,
    ScenarioDialogueModelOutputV1,
)
from services.llm import (
    StructuredCompletion,
    StructuredCompletionInfo,
    StructuredLLMAdapter,
)


class StructuredCompleter(Protocol):
    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        response_model: type[BaseModel],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> StructuredCompletion: ...


class ScenarioDialogueLLMAdapterV1:
    """Constrain an external provider to one evidence-bound NPC line.

    Prompt construction and reference allowlisting belong to
    ``DialogueProjectionService``.  This adapter only invokes the strict JSON
    completion path, revalidates its two-field output, and adds server-owned
    provider provenance.  It intentionally catches nothing: provider and
    validation failures must reach the projection service's deterministic
    fallback boundary.
    """

    def __init__(
        self,
        *,
        completer: StructuredCompleter | None = None,
        model: str | None = None,
    ) -> None:
        self.completer = completer or StructuredLLMAdapter()
        self.model = model

    async def __call__(
        self,
        messages: list[dict[str, str]],
    ) -> ScenarioDialogueExternalCompletionV1:
        return await self.generate(messages)

    async def generate(
        self,
        messages: list[dict[str, str]],
    ) -> ScenarioDialogueExternalCompletionV1:
        completion = await self.completer.complete(
            messages,
            ScenarioDialogueModelOutputV1,
            model=self.model,
            temperature=0.2,
            max_tokens=320,
        )
        info_payload = (
            completion.info.model_dump(mode="python")
            if isinstance(completion.info, BaseModel)
            else completion.info
        )
        info = StructuredCompletionInfo.model_validate(info_payload, strict=True)
        output = ScenarioDialogueModelOutputV1.model_validate(
            completion.output,
            strict=True,
        )
        return ScenarioDialogueExternalCompletionV1.model_validate(
            {
                "output": output,
                "provider": info.provider,
                "model": info.model,
            },
            strict=True,
        )


__all__ = ["ScenarioDialogueLLMAdapterV1"]
