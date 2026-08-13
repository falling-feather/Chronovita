from __future__ import annotations

from array import array
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Protocol, Sequence
import unicodedata
from uuid import uuid4

from services.content.workflow import PublishedLessonResources
from services.contracts.evidence_v1 import (
    EvidencePassageV1,
    EvidenceSourceV1,
    verify_evidence_checksum,
)


INDEX_SCHEMA_VERSION = "chronovita-rag-index/v1"
TOKENIZER_VERSION = "zh-word-bigram/v1"
DEFAULT_VECTOR_MODEL = "BAAI/bge-small-zh-v1.5"
RRF_K = 60

_HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_ASCII_WORD = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")
_TOKEN_SAFE = re.compile(r"^[a-z0-9_\-\.\u3400-\u4dbf\u4e00-\u9fff]+$")
_STOP_HAN = frozenset("的了呢吗啊吧呀和与及是在有把被从到对中里上下来去为这那个其请问说讲谈能可会")
_STOP_BIGRAMS = frozenset(
    {
        "为什么",
        "怎么",
        "如何",
        "什么",
        "请问",
        "告诉",
        "回答",
        "忽略",
        "系统",
        "提示",
        "指令",
        "证据",
        "依据",
        "引用",
        "课程",
        "材料",
        "一下",
        "可以",
        "是否",
    }
)


class RagRetrievalError(RuntimeError):
    """Base error for fail-closed retrieval failures."""


class EvidenceIntegrityError(RagRetrievalError):
    """The sealed evidence passed to the cache no longer verifies."""


class RagIndexUnavailable(RagRetrievalError):
    """The local lexical index cannot be opened or rebuilt."""


class Vectorizer(Protocol):
    model_id: str
    dimension: int

    @property
    def available(self) -> bool: ...

    def embed_passages(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


@dataclass(frozen=True)
class RetrievedPassage:
    passage: EvidencePassageV1
    source: EvidenceSourceV1
    score: float
    relevance: float
    lexical_rank: int | None
    vector_rank: int | None
    matched_signal_count: int
    query_signal_coverage: float
    vector_similarity: float | None


@dataclass(frozen=True)
class RetrievalBatch:
    scope_key: str
    passages: tuple[RetrievedPassage, ...]
    supported: bool
    vector_used: bool


@dataclass(frozen=True)
class _LexicalDocument:
    passage_id: str
    person_ids: str
    signal_tokens: str
    title: str
    summary: str
    body: str
    keywords: str
    people: str

    def metadata_row(self) -> tuple[str, str, str]:
        return (self.passage_id, self.person_ids, self.signal_tokens)

    def fts_row(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.passage_id,
            self.title,
            self.summary,
            self.body,
            self.keywords,
            self.people,
        )


class FastEmbedVectorizer:
    """Offline-only FastEmbed adapter backed by a checksummed model bundle."""

    model_id = DEFAULT_VECTOR_MODEL
    dimension = 512

    def __init__(self, model_root: str | Path, *, enabled: bool = True) -> None:
        self.model_root = Path(model_root)
        self.enabled = enabled
        self._model = None
        self._load_attempted = False
        self._lock = RLock()

    @property
    def available(self) -> bool:
        return self._load_model() is not None

    def embed_passages(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        model = self._required_model()
        vectors = model.embed(list(texts), batch_size=16, parallel=None)
        return [self._normalize_vector(item) for item in vectors]

    def embed_query(self, text: str) -> tuple[float, ...]:
        model = self._required_model()
        query_embed = getattr(model, "query_embed", None)
        vectors = (
            query_embed([text])
            if query_embed is not None
            else model.embed([f"为这个句子生成表示以用于检索相关文章：{text}"])
        )
        return self._normalize_vector(next(iter(vectors)))

    def _required_model(self):
        model = self._load_model()
        if model is None:
            raise RagIndexUnavailable("The local vector model is unavailable.")
        return model

    def _load_model(self):
        with self._lock:
            if self._load_attempted:
                return self._model
            self._load_attempted = True
            if not self.enabled or not _verify_model_bundle(self.model_root):
                return None
            try:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(
                    model_name=self.model_id,
                    specific_model_path=str(self.model_root),
                    local_files_only=True,
                )
            except Exception:
                # Optional provider failures never disable the lexical classroom path.
                self._model = None
            return self._model

    def _normalize_vector(self, value) -> tuple[float, ...]:
        vector = tuple(float(item) for item in value)
        if len(vector) != self.dimension or not all(math.isfinite(item) for item in vector):
            raise RagIndexUnavailable("The vector model returned an invalid embedding.")
        norm = math.sqrt(sum(item * item for item in vector))
        if norm <= 0:
            raise RagIndexUnavailable("The vector model returned a zero embedding.")
        return tuple(item / norm for item in vector)


class HybridEvidenceRetriever:
    def __init__(
        self,
        index_path: str | Path,
        *,
        vectorizer: Vectorizer | None = None,
    ) -> None:
        self.index_path = Path(index_path)
        self.vectorizer = vectorizer
        self._lock = RLock()

    def rebuild(self, resources: PublishedLessonResources) -> None:
        """Explicitly rebuild the derived cache for one exact release scope."""

        self._validate_resources(resources)
        with self._lock:
            self._replace_index_cache(resources)

    def retrieve(
        self,
        resources: PublishedLessonResources,
        question: str,
        *,
        person_id: str | None = None,
        limit: int = 8,
    ) -> RetrievalBatch:
        self._validate_resources(resources)
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")

        lexicon = _scope_lexicon(resources)
        query_tokens = _tokens_for_text(question, lexicon, query=True)
        signal_tokens = frozenset(_signal_tokens(query_tokens))
        scope_key = _scope_key(resources)
        if not signal_tokens:
            return RetrievalBatch(
                scope_key=scope_key,
                passages=(),
                supported=False,
                vector_used=False,
            )

        with self._lock:
            try:
                lexical, vector, document_tokens = self._query_index(
                    resources,
                    question,
                    query_tokens,
                    person_id=person_id,
                )
            except RagIndexUnavailable:
                self._replace_index_cache(resources)
                lexical, vector, document_tokens = self._query_index(
                    resources,
                    question,
                    query_tokens,
                    person_id=person_id,
                )

        passages = {item.passage_id: item for item in resources.evidence_corpus.passages}
        sources = {item.source_id: item for item in resources.evidence_corpus.sources}
        lexical_ranks = {passage_id: rank for rank, (passage_id, _) in enumerate(lexical, 1)}
        vector_ranks = {passage_id: rank for rank, (passage_id, _) in enumerate(vector, 1)}
        vector_scores = dict(vector)
        merged_ids = set(lexical_ranks) | set(vector_ranks)
        scored: list[tuple[str, float]] = []
        for passage_id in merged_ids:
            score = 0.0
            if passage_id in lexical_ranks:
                score += 1.0 / (RRF_K + lexical_ranks[passage_id])
            if passage_id in vector_ranks:
                score += 1.0 / (RRF_K + vector_ranks[passage_id])
            scored.append((passage_id, score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        top_five_ids = [passage_id for passage_id, _ in scored[:5]]
        matched_union = frozenset().union(
            *(
                signal_tokens & document_tokens.get(passage_id, frozenset())
                for passage_id in top_five_ids
            )
        )
        query_signal_coverage = len(matched_union) / len(signal_tokens)

        maximum = scored[0][1] if scored else 1.0
        results: list[RetrievedPassage] = []
        for passage_id, score in scored[:limit]:
            passage = passages.get(passage_id)
            if passage is None:
                raise EvidenceIntegrityError("The derived index references an unknown passage.")
            matched = len(signal_tokens & document_tokens.get(passage_id, frozenset()))
            results.append(
                RetrievedPassage(
                    passage=passage,
                    source=sources[passage.source_id],
                    score=score,
                    relevance=min(1.0, max(0.0, score / maximum)),
                    lexical_rank=lexical_ranks.get(passage_id),
                    vector_rank=vector_ranks.get(passage_id),
                    matched_signal_count=matched,
                    query_signal_coverage=query_signal_coverage,
                    vector_similarity=vector_scores.get(passage_id),
                )
            )

        supported = (
            query_signal_coverage >= 0.40
            and any(item.matched_signal_count >= 1 for item in results[:5])
        ) or any(
            item.vector_similarity is not None and item.vector_similarity >= 0.82
            for item in results[:5]
        )
        return RetrievalBatch(
            scope_key=scope_key,
            passages=tuple(results),
            supported=supported,
            vector_used=bool(vector),
        )

    def _query_index(
        self,
        resources: PublishedLessonResources,
        question: str,
        query_tokens: Sequence[str],
        *,
        person_id: str | None,
    ) -> tuple[
        list[tuple[str, float]],
        list[tuple[str, float]],
        dict[str, frozenset[str]],
    ]:
        connection = self._connect()
        try:
            self._create_schema(connection)
            self._ensure_scope(connection, resources)
            vector_available = self._ensure_vectors(connection, resources)
            scope_key = _scope_key(resources)
            lexical = self._lexical_ranking(
                connection,
                scope_key,
                query_tokens,
                person_id=person_id,
            )
            vector = (
                self._vector_ranking(
                    connection,
                    scope_key,
                    question,
                    person_id=person_id,
                )
                if vector_available
                else []
            )
            document_tokens = self._document_signal_tokens(
                connection,
                scope_key,
            )
            return lexical, vector, document_tokens
        except RagIndexUnavailable:
            raise
        except (sqlite3.Error, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RagIndexUnavailable("The local RAG cache is malformed.") from exc
        finally:
            connection.close()

    def _replace_index_cache(
        self,
        resources: PublishedLessonResources,
    ) -> None:
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            if self.index_path.is_symlink():
                raise RagIndexUnavailable(
                    "The local RAG cache cannot be a symbolic link."
                )
            parent = self.index_path.parent.resolve()
            target = self.index_path.resolve(strict=False)
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise RagIndexUnavailable(
                    "The local RAG cache target must be a regular file."
                )
            temporary = parent / f".{target.name}.{uuid4().hex}.rebuild"
            temporary.touch(mode=0o600, exist_ok=False)
        except RagIndexUnavailable:
            raise
        except OSError as exc:
            raise RagIndexUnavailable("Cannot prepare a replacement RAG cache.") from exc

        moved_sidecars: list[tuple[Path, Path]] = []
        try:
            connection = sqlite3.connect(temporary, timeout=15)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                self._create_schema(connection)
                self._rebuild_lexical_scope(connection, resources)
                self._ensure_vectors(connection, resources)
            finally:
                connection.close()

            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = Path(str(target) + suffix)
                if not sidecar.exists():
                    continue
                if sidecar.is_symlink() or not sidecar.is_file():
                    raise RagIndexUnavailable(
                        "The local RAG cache has an unsafe SQLite sidecar."
                    )
                quarantine = parent / f".{target.name}.{uuid4().hex}{suffix}.stale"
                os.replace(sidecar, quarantine)
                moved_sidecars.append((sidecar, quarantine))
            os.replace(temporary, target)
            self._fsync_file(target)
            self._fsync_directory(parent)
        except RagIndexUnavailable:
            self._restore_sidecars(moved_sidecars)
            self._discard_quarantined_sidecars(moved_sidecars)
            raise
        except (OSError, sqlite3.Error) as exc:
            self._restore_sidecars(moved_sidecars)
            self._discard_quarantined_sidecars(moved_sidecars)
            raise RagIndexUnavailable("Cannot rebuild the local RAG cache.") from exc
        finally:
            try:
                if temporary.exists() and not temporary.is_symlink():
                    temporary.unlink()
            except OSError:
                pass
        self._discard_quarantined_sidecars(moved_sidecars)

    @staticmethod
    def _restore_sidecars(moved: Sequence[tuple[Path, Path]]) -> None:
        for original, quarantine in reversed(moved):
            try:
                if quarantine.exists() and not original.exists():
                    os.replace(quarantine, original)
            except OSError:
                pass

    @staticmethod
    def _discard_quarantined_sidecars(
        moved: Sequence[tuple[Path, Path]],
    ) -> None:
        for _original, quarantine in moved:
            try:
                if quarantine.exists() and not quarantine.is_symlink():
                    quarantine.unlink()
            except OSError:
                pass

    @staticmethod
    def _fsync_file(path: Path) -> None:
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _connect(self) -> sqlite3.Connection:
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            if self.index_path.is_symlink():
                raise RagIndexUnavailable(
                    "The local RAG cache cannot be a symbolic link."
                )
            connection = sqlite3.connect(self.index_path, timeout=15)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 15000")
            return connection
        except RagIndexUnavailable:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RagIndexUnavailable("Cannot open the local RAG index.") from exc

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        try:
            if not connection.execute(
                "SELECT sqlite_compileoption_used('ENABLE_FTS5')"
            ).fetchone()[0]:
                raise RagIndexUnavailable("This SQLite runtime does not provide FTS5.")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rag_scopes (
                    scope_key TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    tokenizer_version TEXT NOT NULL,
                    release_checksum TEXT NOT NULL,
                    evidence_checksum TEXT NOT NULL,
                    corpus_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    lesson_id TEXT NOT NULL,
                    passage_count INTEGER NOT NULL,
                    vector_model TEXT,
                    vector_dimension INTEGER,
                    vector_complete INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS rag_passages (
                    scope_key TEXT NOT NULL,
                    passage_id TEXT NOT NULL,
                    person_ids TEXT NOT NULL,
                    signal_tokens TEXT NOT NULL,
                    vector BLOB,
                    vector_dimension INTEGER,
                    PRIMARY KEY (scope_key, passage_id),
                    FOREIGN KEY (scope_key) REFERENCES rag_scopes(scope_key)
                        ON DELETE CASCADE
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_passages_fts USING fts5(
                    scope_key UNINDEXED,
                    passage_id UNINDEXED,
                    title,
                    summary,
                    body,
                    keywords,
                    people,
                    tokenize = 'unicode61 remove_diacritics 2'
                );
                """
            )
        except RagIndexUnavailable:
            raise
        except sqlite3.Error as exc:
            raise RagIndexUnavailable("Cannot initialize the local RAG index.") from exc

    def _ensure_scope(
        self,
        connection: sqlite3.Connection,
        resources: PublishedLessonResources,
    ) -> None:
        scope_key = _scope_key(resources)
        row = connection.execute(
            "SELECT * FROM rag_scopes WHERE scope_key = ?",
            (scope_key,),
        ).fetchone()
        corpus = resources.evidence_corpus
        documents = _lexical_documents(resources)
        stored_metadata = tuple(
            (
                str(item["passage_id"]),
                str(item["person_ids"]),
                str(item["signal_tokens"]),
            )
            for item in connection.execute(
                """
                SELECT passage_id, person_ids, signal_tokens
                FROM rag_passages
                WHERE scope_key = ?
                ORDER BY passage_id
                """,
                (scope_key,),
            ).fetchall()
        )
        stored_fts = tuple(
            (
                str(item["passage_id"]),
                str(item["title"]),
                str(item["summary"]),
                str(item["body"]),
                str(item["keywords"]),
                str(item["people"]),
            )
            for item in connection.execute(
                """
                SELECT passage_id, title, summary, body, keywords, people
                FROM rag_passages_fts
                WHERE scope_key = ?
                ORDER BY passage_id
                """,
                (scope_key,),
            ).fetchall()
        )
        valid = (
            row is not None
            and row["schema_version"] == INDEX_SCHEMA_VERSION
            and row["tokenizer_version"] == TOKENIZER_VERSION
            and row["release_checksum"] == resources.release_checksum
            and row["evidence_checksum"] == corpus.checksum
            and row["corpus_id"] == corpus.corpus_id
            and row["course_id"] == corpus.course_id
            and row["lesson_id"] == corpus.lesson_id
            and row["passage_count"] == len(corpus.passages)
            and stored_metadata
            == tuple(document.metadata_row() for document in documents)
            and stored_fts == tuple(document.fts_row() for document in documents)
        )
        if not valid:
            self._rebuild_lexical_scope(
                connection,
                resources,
                documents=documents,
            )

    def _rebuild_lexical_scope(
        self,
        connection: sqlite3.Connection,
        resources: PublishedLessonResources,
        *,
        documents: tuple[_LexicalDocument, ...] | None = None,
    ) -> None:
        corpus = resources.evidence_corpus
        scope_key = _scope_key(resources)
        use_documents = documents or _lexical_documents(resources)
        try:
            with connection:
                connection.execute(
                    "DELETE FROM rag_passages_fts WHERE scope_key = ?",
                    (scope_key,),
                )
                connection.execute("DELETE FROM rag_scopes WHERE scope_key = ?", (scope_key,))
                connection.execute(
                    """
                    INSERT INTO rag_scopes (
                        scope_key, schema_version, tokenizer_version,
                        release_checksum, evidence_checksum, corpus_id,
                        course_id, lesson_id, passage_count,
                        vector_model, vector_dimension, vector_complete
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0)
                    """,
                    (
                        scope_key,
                        INDEX_SCHEMA_VERSION,
                        TOKENIZER_VERSION,
                        resources.release_checksum,
                        corpus.checksum,
                        corpus.corpus_id,
                        corpus.course_id,
                        corpus.lesson_id,
                        len(corpus.passages),
                    ),
                )
                for document in use_documents:
                    connection.execute(
                        """
                        INSERT INTO rag_passages (
                            scope_key, passage_id, person_ids, signal_tokens
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            scope_key,
                            document.passage_id,
                            document.person_ids,
                            document.signal_tokens,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO rag_passages_fts (
                            scope_key, passage_id, title, summary, body, keywords, people
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            scope_key,
                            *document.fts_row(),
                        ),
                    )
        except sqlite3.Error as exc:
            raise RagIndexUnavailable("Cannot rebuild the local lexical index.") from exc

    def _ensure_vectors(
        self,
        connection: sqlite3.Connection,
        resources: PublishedLessonResources,
    ) -> bool:
        vectorizer = self.vectorizer
        if vectorizer is None or not vectorizer.available:
            return False
        scope_key = _scope_key(resources)
        row = connection.execute(
            """
            SELECT vector_model, vector_dimension, vector_complete
            FROM rag_scopes WHERE scope_key = ?
            """,
            (scope_key,),
        ).fetchone()
        cached_vectors_valid = (
            row is not None
            and row["vector_model"] == vectorizer.model_id
            and row["vector_dimension"] == vectorizer.dimension
            and row["vector_complete"] == 1
            and connection.execute(
                """
                SELECT COUNT(*) FROM rag_passages
                WHERE scope_key = ? AND vector IS NOT NULL
                    AND vector_dimension = ?
                """,
                (scope_key, vectorizer.dimension),
            ).fetchone()[0]
            == len(resources.evidence_corpus.passages)
        )
        if cached_vectors_valid:
            try:
                cached_vectors_valid = all(
                    len(
                        _unpack_vector(
                            item["vector"],
                            int(item["vector_dimension"]),
                        )
                    )
                    == vectorizer.dimension
                    for item in connection.execute(
                        """
                        SELECT vector, vector_dimension
                        FROM rag_passages
                        WHERE scope_key = ?
                        ORDER BY passage_id
                        """,
                        (scope_key,),
                    ).fetchall()
                )
            except RagIndexUnavailable:
                cached_vectors_valid = False
        if cached_vectors_valid:
            return True

        texts = [
            "\n".join(
                (
                    passage.title,
                    passage.summary,
                    passage.text,
                    "关键词：" + "、".join(passage.keywords),
                    "年代边界：" + passage.chronology_note,
                )
            )
            for passage in resources.evidence_corpus.passages
        ]
        try:
            vectors = vectorizer.embed_passages(texts)
            if len(vectors) != len(texts):
                raise RagIndexUnavailable("The vector model returned an incomplete batch.")
            with connection:
                for passage, vector in zip(resources.evidence_corpus.passages, vectors):
                    if len(vector) != vectorizer.dimension:
                        raise RagIndexUnavailable("A cached vector has the wrong dimension.")
                    connection.execute(
                        """
                        UPDATE rag_passages
                        SET vector = ?, vector_dimension = ?
                        WHERE scope_key = ? AND passage_id = ?
                        """,
                        (
                            _pack_vector(vector),
                            vectorizer.dimension,
                            scope_key,
                            passage.passage_id,
                        ),
                    )
                connection.execute(
                    """
                    UPDATE rag_scopes
                    SET vector_model = ?, vector_dimension = ?, vector_complete = 1
                    WHERE scope_key = ?
                    """,
                    (vectorizer.model_id, vectorizer.dimension, scope_key),
                )
            return True
        except Exception:
            # Vector cache generation is optional; lexical retrieval remains authoritative.
            return False

    def _lexical_ranking(
        self,
        connection: sqlite3.Connection,
        scope_key: str,
        query_tokens: Sequence[str],
        *,
        person_id: str | None,
    ) -> list[tuple[str, float]]:
        terms = list(dict.fromkeys(_signal_tokens(query_tokens)))[:96]
        if not terms:
            return []
        query = " OR ".join(f'"{term}"' for term in terms if _TOKEN_SAFE.fullmatch(term))
        if not query:
            return []
        try:
            rows = connection.execute(
                """
                SELECT passage_id,
                    bm25(rag_passages_fts, 0.0, 0.0, 7.0, 5.0, 1.0, 9.0, 6.0)
                        AS lexical_score
                FROM rag_passages_fts
                WHERE rag_passages_fts MATCH ? AND scope_key = ?
                ORDER BY lexical_score ASC, passage_id ASC
                LIMIT 100
                """,
                (query, scope_key),
            ).fetchall()
        except sqlite3.Error as exc:
            raise RagIndexUnavailable("The lexical query failed.") from exc
        allowed = self._allowed_person_passages(connection, scope_key, person_id)
        return [
            (str(row["passage_id"]), float(row["lexical_score"]))
            for row in rows
            if allowed is None or row["passage_id"] in allowed
        ][:30]

    def _vector_ranking(
        self,
        connection: sqlite3.Connection,
        scope_key: str,
        question: str,
        *,
        person_id: str | None,
    ) -> list[tuple[str, float]]:
        vectorizer = self.vectorizer
        if vectorizer is None:
            return []
        try:
            query = vectorizer.embed_query(question)
        except Exception:
            # Query embedding failures degrade to the lexical ranking.
            return []
        allowed = self._allowed_person_passages(connection, scope_key, person_id)
        try:
            rows = connection.execute(
                """
                SELECT passage_id, vector, vector_dimension
                FROM rag_passages
                WHERE scope_key = ? AND vector IS NOT NULL
                """,
                (scope_key,),
            ).fetchall()
            scored = []
            for row in rows:
                passage_id = str(row["passage_id"])
                if allowed is not None and passage_id not in allowed:
                    continue
                vector = _unpack_vector(row["vector"], int(row["vector_dimension"]))
                if len(query) != len(vector):
                    continue
                scored.append((passage_id, sum(a * b for a, b in zip(query, vector))))
        except (sqlite3.Error, RagIndexUnavailable):
            return []
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:30]

    def _allowed_person_passages(
        self,
        connection: sqlite3.Connection,
        scope_key: str,
        person_id: str | None,
    ) -> set[str] | None:
        if person_id is None:
            return None
        rows = connection.execute(
            "SELECT passage_id, person_ids FROM rag_passages WHERE scope_key = ?",
            (scope_key,),
        ).fetchall()
        return {
            str(row["passage_id"])
            for row in rows
            if person_id in json.loads(row["person_ids"])
        }

    def _document_signal_tokens(
        self,
        connection: sqlite3.Connection,
        scope_key: str,
    ) -> dict[str, frozenset[str]]:
        rows = connection.execute(
            "SELECT passage_id, signal_tokens FROM rag_passages WHERE scope_key = ?",
            (scope_key,),
        ).fetchall()
        return {
            str(row["passage_id"]): frozenset(str(row["signal_tokens"]).split())
            for row in rows
        }

    @staticmethod
    def _validate_resources(resources: PublishedLessonResources) -> None:
        corpus = resources.evidence_corpus
        package = resources.course_package
        if not verify_evidence_checksum(corpus):
            raise EvidenceIntegrityError("The published evidence checksum is invalid.")
        if (
            (corpus.course_id, corpus.lesson_id)
            != (resources.course_id, resources.lesson_id)
            or (package.course_id, package.lesson_id)
            != (resources.course_id, resources.lesson_id)
            or package.content_version != resources.content_version
        ):
            raise EvidenceIntegrityError("The published RAG identities do not agree.")


def _scope_key(resources: PublishedLessonResources) -> str:
    payload = "\0".join(
        (
            INDEX_SCHEMA_VERSION,
            TOKENIZER_VERSION,
            resources.course_id,
            resources.lesson_id,
            resources.release_checksum,
            resources.evidence_corpus.checksum,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scope_lexicon(resources: PublishedLessonResources) -> tuple[str, ...]:
    values = {
        _normalize_text(value)
        for passage in resources.evidence_corpus.passages
        for value in (passage.title, *passage.keywords)
    }
    values.update(_normalize_text(item.name) for item in resources.course_package.people)
    values.update(_normalize_text(item.word) for item in resources.course_package.keywords)
    return tuple(sorted((item for item in values if item), key=lambda item: (-len(item), item)))


def _lexical_documents(
    resources: PublishedLessonResources,
) -> tuple[_LexicalDocument, ...]:
    lexicon = _scope_lexicon(resources)
    people = {
        item.person_id: item.name
        for item in resources.course_package.people
    }
    documents: list[_LexicalDocument] = []
    for passage in resources.evidence_corpus.passages:
        person_names = " ".join(
            people[person_id]
            for person_id in passage.person_ids
            if person_id in people
        )
        fields = {
            "title": _tokens_for_text(passage.title, lexicon),
            "summary": _tokens_for_text(passage.summary, lexicon),
            "body": _tokens_for_text(
                " ".join(
                    filter(
                        None,
                        (
                            passage.text,
                            passage.chronology_note,
                            passage.teaching_note,
                        ),
                    )
                ),
                lexicon,
            ),
            "keywords": _tokens_for_text(" ".join(passage.keywords), lexicon),
            "people": _tokens_for_text(person_names, lexicon),
        }
        all_signals = sorted(
            {
                token
                for values in fields.values()
                for token in _signal_tokens(values)
            }
        )
        documents.append(
            _LexicalDocument(
                passage_id=passage.passage_id,
                person_ids=json.dumps(
                    list(passage.person_ids),
                    separators=(",", ":"),
                ),
                signal_tokens=" ".join(all_signals),
                title=" ".join(fields["title"]),
                summary=" ".join(fields["summary"]),
                body=" ".join(fields["body"]),
                keywords=" ".join(fields["keywords"]),
                people=" ".join(fields["people"]),
            )
        )
    return tuple(documents)


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _tokens_for_text(
    value: str,
    lexicon: Sequence[str],
    *,
    query: bool = False,
) -> tuple[str, ...]:
    normalized = _normalize_text(value)
    tokens: list[str] = []
    for word in _ASCII_WORD.findall(normalized):
        tokens.append(f"a_{word}")
    for run in _HAN_RUN.findall(normalized):
        if len(run) == 1 and run not in _STOP_HAN:
            tokens.append(f"u_{run}")
        for left, right in zip(run, run[1:]):
            pair = left + right
            if pair not in _STOP_BIGRAMS and not (left in _STOP_HAN and right in _STOP_HAN):
                tokens.append(f"b_{pair}")
        if not query:
            tokens.extend(f"u_{char}" for char in run if char not in _STOP_HAN)
    for term in lexicon:
        if term and term in normalized:
            if term not in _STOP_BIGRAMS:
                tokens.append(f"w_{term}")
    return tuple(dict.fromkeys(tokens))


def _signal_tokens(tokens: Sequence[str]):
    return (
        token
        for token in tokens
        if token.startswith(("a_", "b_", "w_", "u_"))
    )


def _pack_vector(vector: Sequence[float]) -> bytes:
    return array("f", (float(item) for item in vector)).tobytes()


def _unpack_vector(payload: bytes, dimension: int) -> tuple[float, ...]:
    values = array("f")
    try:
        values.frombytes(payload)
    except (TypeError, ValueError) as exc:
        raise RagIndexUnavailable("A cached vector is malformed.") from exc
    if len(values) != dimension or not all(math.isfinite(item) for item in values):
        raise RagIndexUnavailable("A cached vector is malformed.")
    return tuple(float(item) for item in values)


def _verify_model_bundle(model_root: Path) -> bool:
    manifest_path = model_root / "model-resource.json"
    if (
        model_root.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.is_symlink()
    ):
        return False
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            set(payload)
            != {
                "schema_version",
                "model_id",
                "source_repository",
                "source_revision",
                "dimension",
                "license",
                "license_url",
                "files",
            }
            or payload["schema_version"] != "rag-model-resource/v1"
            or payload["model_id"] != DEFAULT_VECTOR_MODEL
            or payload["source_repository"] != "Qdrant/bge-small-zh-v1.5"
            or payload["source_revision"]
            != "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
            or payload["dimension"] != 512
            or payload["license"] != "MIT"
            or payload["license_url"]
            != "https://huggingface.co/BAAI/bge-small-zh-v1.5"
            or not isinstance(payload["files"], list)
            or not payload["files"]
        ):
            return False
        normalized = []
        for item in payload["files"]:
            if set(item) != {"path", "sha256", "bytes"}:
                return False
            relative = Path(item["path"])
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or isinstance(item["bytes"], bool)
                or not isinstance(item["bytes"], int)
                or item["bytes"] <= 0
            ):
                return False
            target = model_root / relative
            resolved_target = target.resolve()
            if (
                not resolved_target.is_relative_to(model_root.resolve())
                or not target.is_file()
                or target.is_symlink()
                or target.stat().st_size != item["bytes"]
            ):
                return False
            digest = _file_sha256(target)
            if digest != item["sha256"]:
                return False
            normalized.append(relative.as_posix())
        return normalized == sorted(set(normalized))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_VECTOR_MODEL",
    "EvidenceIntegrityError",
    "FastEmbedVectorizer",
    "HybridEvidenceRetriever",
    "RagIndexUnavailable",
    "RagRetrievalError",
    "RetrievalBatch",
    "RetrievedPassage",
    "Vectorizer",
]
