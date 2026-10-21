from services.ai.contracts import (
    ActionClassificationV1,
    ClassifierModelOutputV1,
    NarratorModelOutputV1,
)


def __getattr__(name: str):
    if name in {"ActionClassifierV1", "PROMPT_POLICY_VERSION"}:
        from services.ai.classifier import (
            PROMPT_POLICY_VERSION,
            ActionClassifierV1,
        )

        return {
            "ActionClassifierV1": ActionClassifierV1,
            "PROMPT_POLICY_VERSION": PROMPT_POLICY_VERSION,
        }[name]
    if name in {"HistoricalNarratorV1", "NARRATOR_POLICY_VERSION"}:
        from services.ai.narrator import (
            NARRATOR_POLICY_VERSION,
            HistoricalNarratorV1,
        )

        return {
            "HistoricalNarratorV1": HistoricalNarratorV1,
            "NARRATOR_POLICY_VERSION": NARRATOR_POLICY_VERSION,
        }[name]
    if name == "ScenarioDialogueLLMAdapterV1":
        from services.ai.dialogue import ScenarioDialogueLLMAdapterV1

        return ScenarioDialogueLLMAdapterV1
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ActionClassificationV1",
    "ActionClassifierV1",
    "ClassifierModelOutputV1",
    "HistoricalNarratorV1",
    "NARRATOR_POLICY_VERSION",
    "NarratorModelOutputV1",
    "PROMPT_POLICY_VERSION",
    "ScenarioDialogueLLMAdapterV1",
]
