from services.ai.contracts import (
    ActionClassificationV1,
    ClassifierModelOutputV1,
)


def __getattr__(name: str):
    if name in {"ActionClassifierV1", "PROMPT_POLICY_VERSION"}:
        from services.ai.classifier import (
            ActionClassifierV1,
            PROMPT_POLICY_VERSION,
        )

        return {
            "ActionClassifierV1": ActionClassifierV1,
            "PROMPT_POLICY_VERSION": PROMPT_POLICY_VERSION,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ActionClassificationV1",
    "ActionClassifierV1",
    "ClassifierModelOutputV1",
    "PROMPT_POLICY_VERSION",
]
