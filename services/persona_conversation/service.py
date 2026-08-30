from __future__ import annotations

import re
from dataclasses import dataclass

from services.content import workflow as content_workflow
from services.contracts.evidence_v1 import (
    RagAnswerV1,
    RagAskRequestV1,
    RagCitationV1,
)
from services.contracts.evidence_v2 import EvidenceCorpusV2
from services.contracts.persona_v1 import PersonaPackV1, PersonaProfileBindingV1
from services.contracts.release_v2 import CourseReleaseManifestV5
from services.rag import RagAnswerService
from services.rag.service import ModelGenerator

from .models import (
    MAX_CONVERSATION_TURNS,
    PersonaConversationIdentityV1,
    PersonaConversationTurnInputV1,
    PersonaConversationTurnV1,
    PersonaConversationV1,
    new_persona_conversation,
)
from .store import (
    PersonaConversationLimitReached,
    PersonaConversationStore,
    PersonaConversationWriteConflict,
    PersonaMessageIdConflict,
)


class PersonaConversationReleaseUnavailable(LookupError):
    code = "persona_release_unavailable"


class PersonaConversationPersonUnavailable(LookupError):
    code = "persona_person_unavailable"


class PersonaConversationReleaseChanged(RuntimeError):
    code = "persona_release_changed"


class PersonaConversationBindingInvalid(RuntimeError):
    code = "persona_binding_invalid"


@dataclass(frozen=True)
class PersonaConversationMessageResult:
    conversation: PersonaConversationV1
    answer: RagAnswerV1
    reused: bool
    continuity_applied: bool


class PersonaConversationCoordinator:
    """Coordinate bounded persona memory around the current immutable V5 release.

    Conversation turns are display memory only. Every answer still goes through the
    RAG service, which performs a fresh retrieval scoped by the current PersonaPack;
    remembered passage IDs and answer snapshots are never supplied as evidence.
    """

    def __init__(
        self,
        store: PersonaConversationStore,
        rag_service: RagAnswerService,
    ) -> None:
        self.store = store
        self.rag_service = rag_service

    def create_conversation(
        self,
        *,
        owner_user_id: str,
        course_id: str,
        lesson_id: str,
        person_id: str,
    ) -> PersonaConversationV1:
        resources, pack, _profile = _load_current_persona_binding(
            course_id,
            lesson_id,
            person_id,
        )
        identity = PersonaConversationIdentityV1(
            owner_user_id=owner_user_id,
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            release_id=resources.release_id,
            release_no=resources.release_no,
            release_checksum=resources.release_checksum,
            persona_pack_id=pack.pack_id,
            persona_pack_version=pack.pack_version,
            persona_pack_checksum=pack.checksum,
            evidence_corpus_id=resources.evidence_corpus.corpus_id,
            evidence_version=resources.evidence_corpus.corpus_version,
            evidence_checksum=resources.evidence_corpus.checksum,
            person_id=person_id,
            channel="consult",
        )
        record = self.store.create_conversation(new_persona_conversation(identity))
        return record.conversation

    def get_conversation(
        self,
        conversation_id: str,
        *,
        owner_user_id: str,
    ) -> PersonaConversationV1:
        return self.store.load_conversation(
            conversation_id,
            owner_user_id=owner_user_id,
        ).conversation

    async def send_message(
        self,
        conversation_id: str,
        *,
        owner_user_id: str,
        client_message_id: str,
        expected_revision: int,
        question: str,
        external_generator: ModelGenerator | None = None,
    ) -> PersonaConversationMessageResult:
        record = self.store.load_conversation(
            conversation_id,
            owner_user_id=owner_user_id,
        )
        conversation = record.conversation
        resources, _pack, _profile = _load_current_persona_binding(
            conversation.course_id,
            conversation.lesson_id,
            conversation.person_id,
        )
        _require_same_release(conversation, resources)

        existing = next(
            (
                turn
                for turn in conversation.turns
                if turn.client_message_id == client_message_id
            ),
            None,
        )
        if existing is not None and existing.question != question.strip():
            raise PersonaMessageIdConflict(
                "client_message_id was already used for a different question"
            )
        if existing is not None:
            return PersonaConversationMessageResult(
                conversation=conversation,
                answer=_answer_from_stored_turn(resources, conversation, existing),
                reused=True,
                continuity_applied=False,
            )
        if conversation.revision != expected_revision:
            raise PersonaConversationWriteConflict(
                "persona conversation revision changed"
            )
        if len(conversation.turns) >= MAX_CONVERSATION_TURNS:
            raise PersonaConversationLimitReached(
                f"persona conversation is limited to {MAX_CONVERSATION_TURNS} turns"
            )

        resolved_question, continuity_applied = _resolve_continuation_question(
            question,
            conversation,
        )
        answer = await self.rag_service.ask(
            RagAskRequestV1(
                course_id=conversation.course_id,
                lesson_id=conversation.lesson_id,
                persona_mode="person",
                person_id=conversation.person_id,
                question=resolved_question,
            ),
            external_generator=external_generator,
        )
        _require_answer_identity(conversation, answer)
        turn_input = _turn_input_from_answer(
            resources.evidence_corpus,
            client_message_id=client_message_id,
            question=question,
            answer=answer,
        )
        try:
            appended = self.store.append_turn(
                conversation_id,
                owner_user_id=owner_user_id,
                expected_revision=expected_revision,
                turn=turn_input,
            )
        except PersonaMessageIdConflict:
            # Two identical HTTP retries can finish generation in a different
            # order and therefore produce different display snapshots.  The
            # first committed turn is authoritative; a later completion with
            # the same client message and question must replay that winner
            # instead of exposing provider nondeterminism as a 409.
            latest = self.store.load_conversation(
                conversation_id,
                owner_user_id=owner_user_id,
            ).conversation
            concurrent = next(
                (
                    turn
                    for turn in latest.turns
                    if turn.client_message_id == client_message_id
                ),
                None,
            )
            if concurrent is None or concurrent.question != question.strip():
                raise
            return PersonaConversationMessageResult(
                conversation=latest,
                answer=_answer_from_stored_turn(resources, latest, concurrent),
                reused=True,
                continuity_applied=False,
            )
        stable_answer = (
            _answer_from_stored_turn(
                resources,
                appended.conversation,
                appended.turn,
            )
            if appended.reused
            else answer
        )
        return PersonaConversationMessageResult(
            conversation=appended.conversation,
            answer=stable_answer,
            reused=appended.reused,
            continuity_applied=(continuity_applied and not appended.reused),
        )


def _load_current_persona_binding(
    course_id: str,
    lesson_id: str,
    person_id: str,
) -> tuple[
    content_workflow.PublishedLessonResources,
    PersonaPackV1,
    PersonaProfileBindingV1,
]:
    release = content_workflow.get_current_release(course_id)
    if not isinstance(release, CourseReleaseManifestV5):
        raise PersonaConversationReleaseUnavailable(
            "当前课程尚未发布人物会话所需的 V5 资源。"
        )
    try:
        resources = content_workflow.get_published_lesson_resources(
            course_id,
            lesson_id,
        )
    except content_workflow.ContentNotFound as exc:
        raise PersonaConversationReleaseUnavailable(
            "当前课时尚未发布人物会话资源。"
        ) from exc
    pack = resources.persona_pack
    if pack is None or not isinstance(resources.evidence_corpus, EvidenceCorpusV2):
        raise PersonaConversationReleaseUnavailable(
            "当前课时的人物包或原子证据库尚未发布。"
        )
    if (
        pack.course_id != resources.course_id
        or pack.lesson_id != resources.lesson_id
        or pack.course_checksum != resources.course_package.checksum
        or pack.evidence_corpus_id != resources.evidence_corpus.corpus_id
        or pack.evidence_version != resources.evidence_corpus.corpus_version
        or pack.evidence_checksum != resources.evidence_corpus.checksum
    ):
        raise PersonaConversationBindingInvalid(
            "当前人物包与课程或证据发布绑定不一致。"
        )
    profile = next(
        (
            item
            for item in pack.profiles
            if item.person_id == person_id and "consult" in item.channels
        ),
        None,
    )
    if profile is None:
        raise PersonaConversationPersonUnavailable(
            "当前发布课程中不存在可召见的该人物或群体。"
        )
    return resources, pack, profile


def _require_same_release(
    conversation: PersonaConversationV1,
    resources: content_workflow.PublishedLessonResources,
) -> None:
    pack = resources.persona_pack
    if pack is None or (
        conversation.release_id != resources.release_id
        or conversation.release_no != resources.release_no
        or conversation.release_checksum != resources.release_checksum
        or conversation.persona_pack_id != pack.pack_id
        or conversation.persona_pack_version != pack.pack_version
        or conversation.persona_pack_checksum != pack.checksum
        or conversation.evidence_corpus_id != resources.evidence_corpus.corpus_id
        or conversation.evidence_version != resources.evidence_corpus.corpus_version
        or conversation.evidence_checksum != resources.evidence_corpus.checksum
    ):
        raise PersonaConversationReleaseChanged(
            "课程发布已更新，请基于当前发布建立新会话。"
        )


def _require_answer_identity(
    conversation: PersonaConversationV1,
    answer: RagAnswerV1,
) -> None:
    if (
        answer.course_id != conversation.course_id
        or answer.lesson_id != conversation.lesson_id
        or answer.release_id != conversation.release_id
        or answer.release_no != conversation.release_no
        or answer.release_checksum != conversation.release_checksum
        or answer.evidence_corpus_id != conversation.evidence_corpus_id
        or answer.evidence_version != conversation.evidence_version
        or answer.evidence_checksum != conversation.evidence_checksum
    ):
        raise PersonaConversationReleaseChanged(
            "课程发布在回答期间发生变化，请基于当前发布建立新会话。"
        )
    if answer.persona_mode != "person" or answer.person_id != conversation.person_id:
        raise PersonaConversationBindingInvalid("人物回答与会话固定发布身份不一致。")


def _answer_from_stored_turn(
    resources: content_workflow.PublishedLessonResources,
    conversation: PersonaConversationV1,
    turn: PersonaConversationTurnV1,
) -> RagAnswerV1:
    """Rebuild an idempotent response without a second retrieval or API call."""

    source_by_id = {item.source_id: item for item in resources.evidence_corpus.sources}
    passage_by_id = {
        item.passage_id: item for item in resources.evidence_corpus.passages
    }
    if any(
        passage_id not in passage_by_id for passage_id in turn.retrieved_passage_ids
    ):
        raise PersonaConversationBindingInvalid(
            "已保存会话的召回记录不再属于固定证据库。"
        )
    citations = []
    for rank, passage_id in enumerate(turn.passage_ids, 1):
        passage = passage_by_id.get(passage_id)
        if passage is None or passage.source_id not in source_by_id:
            raise PersonaConversationBindingInvalid(
                "已保存会话引用不再属于固定证据库。"
            )
        source = source_by_id[passage.source_id]
        citations.append(
            RagCitationV1(
                citation_id=f"rag-citation-{rank:02d}",
                passage_id=passage.passage_id,
                source_id=source.source_id,
                source_title=source.title,
                locator=passage.source_locator,
                excerpt=passage.text,
                relevance=1.0,
                certainty=passage.certainty,
            )
        )
    return RagAnswerV1(
        answer_source=turn.answer_source,
        retrieval_mode=turn.retrieval_mode,
        body=turn.answer_snapshot,
        persona_mode="person",
        person_id=conversation.person_id,
        role_disclaimer="角色化教学表达，不是史料原话。",
        citations=tuple(citations),
        retrieved_passage_ids=turn.retrieved_passage_ids,
        course_id=conversation.course_id,
        lesson_id=conversation.lesson_id,
        release_id=conversation.release_id,
        release_no=conversation.release_no,
        release_checksum=conversation.release_checksum,
        evidence_corpus_id=conversation.evidence_corpus_id,
        evidence_version=conversation.evidence_version,
        evidence_checksum=conversation.evidence_checksum,
        uncertainty=turn.uncertainty,
    )


def _turn_input_from_answer(
    corpus: EvidenceCorpusV2,
    *,
    client_message_id: str,
    question: str,
    answer: RagAnswerV1,
) -> PersonaConversationTurnInputV1:
    passage_ids = tuple(item.passage_id for item in answer.citations)
    passages = {
        item.passage_id: item
        for item in corpus.passages
        if item.passage_id in passage_ids
    }
    slot_ids = tuple(
        sorted(
            {
                slot_id
                for passage in passages.values()
                for slot_id in passage.answer_slot_ids
            }
        )
    )
    boundary_ids = tuple(
        sorted(
            {
                boundary_id
                for passage in passages.values()
                for boundary_id in passage.boundary_ids
            }
        )
    )
    if answer.answer_source == "model":
        route_target = "external_api"
        route_reason = "grounded_complex_question"
    elif answer.answer_source == "extractive":
        route_target = "local_template"
        route_reason = "local_grounded_answer"
    elif "指代或范围还不够清楚" in answer.body:
        route_target = "clarify"
        route_reason = "ambiguous_question"
    else:
        route_target = "refuse"
        route_reason = "insufficient_or_disallowed_question"
    return PersonaConversationTurnInputV1(
        client_message_id=client_message_id,
        question=question,
        answer_snapshot=answer.body,
        route_target=route_target,
        route_reason=route_reason,
        answer_source=answer.answer_source,
        uncertainty=answer.uncertainty,
        retrieval_mode=answer.retrieval_mode,
        slot_ids=slot_ids[:12],
        boundary_ids=boundary_ids[:12],
        passage_ids=passage_ids[:12],
        retrieved_passage_ids=answer.retrieved_passage_ids[:12],
    )


_CONTINUATION_PATTERN = re.compile(
    r"^(?:那|这|它|其|此|再|那么|所以|然后|还有|为什么呢|具体呢|后来呢)"
)


def _resolve_continuation_question(
    question: str,
    conversation: PersonaConversationV1,
) -> tuple[str, bool]:
    normalized = question.strip()
    if (
        not conversation.turns
        or len(normalized) > 80
        or _CONTINUATION_PATTERN.search(normalized) is None
    ):
        return normalized, False
    previous = conversation.turns[-1].question
    prefix = "上一问："
    separator = "；当前追问："
    available = max(0, 400 - len(prefix) - len(separator) - len(normalized))
    previous = previous[:available]
    return f"{prefix}{previous}{separator}{normalized}", True


__all__ = [
    "PersonaConversationBindingInvalid",
    "PersonaConversationCoordinator",
    "PersonaConversationMessageResult",
    "PersonaConversationPersonUnavailable",
    "PersonaConversationReleaseChanged",
    "PersonaConversationReleaseUnavailable",
]
