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
from .local_reply import (
    LOCAL_REPLY_VERSION,
    LocalReplyFit,
    LocalResponseMode,
    detect_unsupported_answer_slot,
    fit_local_reply,
)
from .routing import (
    RAG_ROUTER_VERSION,
    EvidenceConfidence,
    RagRouteDecision,
    RagRouteTarget,
    route_rag_query,
)
from .service import (
    ROLE_DISCLAIMER,
    RagAnswerService,
    RagExternalAnswerUnavailable,
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
    "LOCAL_REPLY_VERSION",
    "QUERY_PLANNER_VERSION",
    "RAG_ROUTER_VERSION",
    "EvidenceConfidence",
    "LocalReplyFit",
    "LocalResponseMode",
    "QueryIntent",
    "ROLE_DISCLAIMER",
    "RagAnswerService",
    "RagExternalAnswerUnavailable",
    "RagIndexUnavailable",
    "RagPersonNotFound",
    "RagQueryPlan",
    "RagRouteDecision",
    "RagRouteTarget",
    "RagRetrievalError",
    "RagServiceUnavailable",
    "RetrievalBatch",
    "RetrievedPassage",
    "Vectorizer",
    "configure_rag",
    "detect_unsupported_answer_slot",
    "fit_local_reply",
    "get_rag_service",
    "plan_rag_query",
    "route_rag_query",
    "shutdown_rag",
    "structured_model_generator",
]
