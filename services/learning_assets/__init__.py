from __future__ import annotations

import threading

from sqlalchemy.engine import Engine

from .store import (
    FeedbackCreateResult,
    LearningAssetStore,
    LearningAssetStoreError,
    LearningFeedbackIntegrityError,
    LearningSubmissionConflict,
    LearningSubmissionIntegrityError,
    LearningSubmissionNotFound,
    SubmissionCreateResult,
    learning_feedback_table,
    learning_submissions_table,
)


_LOCK = threading.RLock()
_STORE: LearningAssetStore | None = None


def configure_learning_assets(engine: Engine) -> LearningAssetStore:
    global _STORE
    with _LOCK:
        if _STORE is not None and _STORE.engine is not engine:
            raise RuntimeError("learning asset store is already configured")
        if _STORE is None:
            _STORE = LearningAssetStore(engine)
        return _STORE


def get_learning_assets() -> LearningAssetStore:
    with _LOCK:
        if _STORE is None:
            raise RuntimeError("learning asset store is not configured")
        return _STORE


def shutdown_learning_assets() -> None:
    global _STORE
    with _LOCK:
        _STORE = None


__all__ = [
    "FeedbackCreateResult",
    "LearningAssetStore",
    "LearningAssetStoreError",
    "LearningFeedbackIntegrityError",
    "LearningSubmissionConflict",
    "LearningSubmissionIntegrityError",
    "LearningSubmissionNotFound",
    "SubmissionCreateResult",
    "configure_learning_assets",
    "get_learning_assets",
    "learning_feedback_table",
    "learning_submissions_table",
    "shutdown_learning_assets",
]
