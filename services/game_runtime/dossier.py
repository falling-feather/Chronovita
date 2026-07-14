from __future__ import annotations

import hashlib

from pydantic import ValidationError

from services.contracts.v1 import (
    DossierChoiceV1,
    DossierV1,
    GameSessionV1,
    KnowledgeNodeV1,
    RuntimeBundleV1,
    StateSnapshotV1,
    calculate_contract_checksum,
)
from services.game_runtime import SituationEngineV1


class DossierGenerationError(ValueError):
    pass


def build_final_dossier(
    engine: SituationEngineV1,
    session: GameSessionV1,
) -> tuple[GameSessionV1, DossierV1]:
    if session.status != "completed" or session.ending_id is None:
        raise DossierGenerationError(
            "a final dossier requires a completed session with an ending"
        )
    if session.ended_at is None:
        raise DossierGenerationError(
            "a final dossier requires a completed session timestamp"
        )

    ending = next(
        (
            item
            for item in engine.scenario.ending_rules
            if item.ending_id == session.ending_id
        ),
        None,
    )
    if ending is None:
        raise DossierGenerationError(
            f"session ending is not present in its pinned scenario: {session.ending_id}"
        )

    dossier_id = dossier_id_for_session(session.session_id)
    if session.dossier_id not in {None, dossier_id}:
        raise DossierGenerationError(
            "session references a non-deterministic dossier identity"
        )
    session_payload = session.model_dump(mode="json")
    session_payload["dossier_id"] = dossier_id
    attached_session = GameSessionV1.model_validate(session_payload)

    action_rules = {
        item.action_id: item
        for item in engine.scenario.action_rules
    }
    key_choices = [
        DossierChoiceV1(
            turn_id=turn.turn_id,
            turn_no=turn.turn_no,
            action_id=turn.classified_action_id,
            choice=turn.raw_input,
            consequence=turn.narrative,
        )
        for turn in attached_session.turns
        if turn.status == "applied"
    ]
    action_labels = [
        action_rules[choice.action_id].label
        for choice in key_choices
    ]
    strategy_summary = " -> ".join(action_labels) or ending.summary

    fact_refs = _ordered_unique(
        [
            fact_id
            for turn in attached_session.turns
            for fact_id in turn.fact_refs
        ]
        + list(ending.fact_refs)
    )
    facts = {item.fact_id: item for item in engine.course.facts}
    source_ref_ids = _ordered_unique(
        [
            source_id
            for fact_id in fact_refs
            for source_id in facts[fact_id].source_ref_ids
        ]
        + list(ending.source_ref_ids)
    )

    knowledge_nodes = []
    if "concept" in engine.scenario.dossier_template.knowledge_node_kinds:
        knowledge_nodes = [
            KnowledgeNodeV1(
                node_id=_derived_id("knowledge", fact.fact_id),
                label=fact.statement,
                kind="concept",
                summary=fact.teacher_note,
                source_ref_ids=list(fact.source_ref_ids),
            )
            for fact_id in fact_refs
            for fact in [facts[fact_id]]
        ]

    title = engine.scenario.dossier_template.title_template.replace(
        "{scenario_title}",
        engine.scenario.title,
    ).strip()
    if not title:
        raise DossierGenerationError("dossier title template rendered empty")

    initial_state = {
        item.variable_id: item.initial
        for item in engine.scenario.variables
    }
    dossier = DossierV1(
        dossier_id=dossier_id,
        session_id=attached_session.session_id,
        user_id=attached_session.user_id,
        course_id=attached_session.course_id,
        lesson_id=attached_session.lesson_id,
        scenario_id=attached_session.scenario_id,
        course_content_version=attached_session.course_content_version,
        scenario_version=attached_session.scenario_version,
        course_checksum=attached_session.course_checksum,
        scenario_checksum=attached_session.scenario_checksum,
        status="final",
        title=title,
        ending_id=attached_session.ending_id,
        strategy_summary=strategy_summary,
        key_choices=key_choices,
        state_trajectory=[
            StateSnapshotV1(turn_no=0, state=initial_state),
            *[
                StateSnapshotV1(
                    turn_no=turn.turn_no,
                    state=dict(turn.state_after),
                )
                for turn in attached_session.turns
            ],
        ],
        major_costs=list(ending.major_costs),
        historical_explanation=ending.historical_explanation,
        knowledge_nodes=knowledge_nodes,
        knowledge_edges=[],
        follow_up_questions=list(
            engine.scenario.dossier_template.reflection_questions
        ),
        reflection_notes=[],
        fact_refs=fact_refs,
        source_ref_ids=source_ref_ids,
        generated_at=attached_session.ended_at,
        checksum="0" * 64,
    )
    dossier_payload = dossier.model_dump(mode="json")
    dossier_payload["checksum"] = calculate_contract_checksum(dossier)
    dossier = DossierV1.model_validate(dossier_payload)

    try:
        bundle = RuntimeBundleV1.model_validate(
            {
                "course": engine.course.model_dump(mode="json"),
                "scenario": engine.scenario.model_dump(mode="json"),
                "session": attached_session.model_dump(mode="json"),
                "dossier": dossier.model_dump(mode="json"),
            }
        )
    except ValidationError as exc:
        raise DossierGenerationError(
            f"generated dossier failed runtime bundle validation: {exc}"
        ) from exc
    if bundle.session is None or bundle.dossier is None:
        raise DossierGenerationError("generated runtime bundle lost dossier data")
    return bundle.session, bundle.dossier


def dossier_id_for_session(session_id: str) -> str:
    return _derived_id("dossier", session_id)


def _derived_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = [
    "DossierGenerationError",
    "build_final_dossier",
    "dossier_id_for_session",
]
