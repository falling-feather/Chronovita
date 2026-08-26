from __future__ import annotations

from pathlib import Path
from threading import RLock

from .retrieval import (
    DEFAULT_VECTOR_MODEL,
    EvidenceIntegrityError,
    FastEmbedVectorizer,
    HybridEvidenceRetriever,
    RagIndexUnavailable,
    RagRetrievalError,
    RetrievalBatch,
    RetrievedPassage,
    Vectorizer,
)
from .query import (
    QUERY_PLANNER_VERSION,
    QueryIntent,
    RagQueryPlan,
    plan_rag_query,
)
from .service import (
    ROLE_DISCLAIMER,
    RagAnswerService,
    RagPersonNotFound,
    structured_model_generator,
)


_LOCK = RLock()
_SERVICE: RagAnswerService | None = None


class RagServiceUnavailable(RuntimeError):
    pass


def configure_rag(
    *,
    index_path: str | Path,
    model_root: str | Path,
    vector_enabled: bool = True,
    vectorizer: Vectorizer | None = None,
) -> RagAnswerService:
    global _SERVICE
    selected_vectorizer = vectorizer
    if selected_vectorizer is None:
        selected_vectorizer = FastEmbedVectorizer(
            model_root,
            enabled=vector_enabled,
        )
    service = RagAnswerService(
        HybridEvidenceRetriever(index_path, vectorizer=selected_vectorizer)
    )
    with _LOCK:
        _SERVICE = service
    return service


def get_rag_service() -> RagAnswerService:
    with _LOCK:
        if _SERVICE is None:
            raise RagServiceUnavailable("RAG service is not configured.")
        return _SERVICE


def shutdown_rag() -> None:
    global _SERVICE
    with _LOCK:
        _SERVICE = None


__all__ = [
    "DEFAULT_VECTOR_MODEL",
    "EvidenceIntegrityError",
    "FastEmbedVectorizer",
    "HybridEvidenceRetriever",
    "QUERY_PLANNER_VERSION",
    "QueryIntent",
    "ROLE_DISCLAIMER",
    "RagAnswerService",
    "RagIndexUnavailable",
    "RagPersonNotFound",
    "RagQueryPlan",
    "RagRetrievalError",
    "RagServiceUnavailable",
    "RetrievalBatch",
    "RetrievedPassage",
    "Vectorizer",
    "configure_rag",
    "get_rag_service",
    "plan_rag_query",
    "shutdown_rag",
    "structured_model_generator",
]
