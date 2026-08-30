"""Sealed persona bindings for the L101 flagship lesson.

The pack contains presentation policy and stable artifact references only.  It
does not copy course or evidence prose, and it cannot widen the knowledge scope
published by EvidenceCorpusV2.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.contracts.persona_v1 import (
    PersonaEvidenceUseV1,
    PersonaPackV1,
    PersonaProfileBindingV1,
    PersonaVoiceV1,
    ScenarioVoiceBindingV1,
    sign_persona_pack,
)

DAYU_PERSONA_CREATED_AT = datetime(2026, 8, 30, 21, 0, tzinfo=timezone.utc)
DAYU_COURSE_CHECKSUM = (
    "8bdd1ed01fd56b4ef92d6760dbca60b28b81dcaac8d15d2f4dbc5c92645b15f5"
)
DAYU_SCENARIO_CHECKSUM = (
    "8bd70a0e3f6dded9b6f6a24196ef79cd5009b0da9efc59c97fcd1a7926650d63"
)
DAYU_EVIDENCE_CHECKSUM = (
    "723fb44df49358d810bcc2ecfa895c25c950da9a0b5387d38b2fad17334f920b"
)


def _voice(
    perspective: str,
    register: str,
    *tone_tags: str,
    length_policy: str = "standard",
) -> PersonaVoiceV1:
    return PersonaVoiceV1(
        perspective=perspective,
        register=register,
        tone_tags=tuple(sorted(tone_tags)),
        length_policy=length_policy,
    )


def _evidence(*items: tuple[str, str]) -> tuple[PersonaEvidenceUseV1, ...]:
    return tuple(
        PersonaEvidenceUseV1(passage_id=passage_id, mode=mode)
        for passage_id, mode in sorted(items)
    )


def _binding(
    binding_id: str,
    action_id: str,
    person_id: str,
) -> ScenarioVoiceBindingV1:
    return ScenarioVoiceBindingV1(
        binding_id=binding_id,
        node_id="global-rule-set",
        action_id=action_id,
        person_id=person_id,
    )


def build_dayu_persona_pack_v1(
    *,
    sealed_at: datetime = DAYU_PERSONA_CREATED_AT,
    sealed_by: str = "chronovita-content-team",
) -> PersonaPackV1:
    """Build the deterministic five-profile L101 persona pack."""

    profiles = (
        PersonaProfileBindingV1(
            person_id="person-7c4825d9",
            persona_kind="transmitted_memory",
            channels=("consult", "scenario"),
            voice=_voice(
                "first_person_limited",
                "克制而负责，只在传世记忆允许的范围内谈治水取舍，并主动承认年代距离。",
                "cautious",
                "evidence-aware",
                "public-minded",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "dayu-slot-erlitou-xia-boundary",
                        "dayu-slot-methods",
                        "dayu-slot-revise-with-new-evidence",
                        "dayu-slot-source-layers",
                        "dayu-slot-three-doors",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "dayu-b-absence",
                        "dayu-b-causation",
                        "dayu-b-erlitou-name",
                        "dayu-b-legend-detail",
                        "dayu-b-modern-waterwork",
                        "dayu-b-persona",
                        "dayu-b-transmitted-distance",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("dayu-p004", "role_voice"),
                ("dayu-p006", "boundary_only"),
                ("dayu-p007", "role_voice"),
                ("dayu-p023", "boundary_only"),
                ("dayu-p026", "boundary_only"),
            ),
            portrait_asset_key="L101-yu",
        ),
        PersonaProfileBindingV1(
            person_id="person-b40a4965",
            persona_kind="transmitted_memory",
            channels=("consult",),
            voice=_voice(
                "first_person_limited",
                "从紧迫防护和方案受限的角度提出异议，不把后世成败评价冒充本人供词。",
                "cautious",
                "defensive",
                "plain",
                length_policy="brief",
            ),
            focus_answer_slot_ids=(
                "dayu-slot-source-layers",
                "dayu-slot-three-doors",
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "dayu-b-modern-waterwork",
                        "dayu-b-persona",
                        "dayu-b-transmitted-distance",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("dayu-p004", "role_voice"),
                ("dayu-p031", "boundary_only"),
            ),
            portrait_asset_key="L101-gun",
        ),
        PersonaProfileBindingV1(
            person_id="person-31118bee",
            persona_kind="transmitted_memory",
            channels=("consult", "scenario"),
            voice=_voice(
                "first_person_limited",
                "重视记录、复核和协作；传世叙事之外的问题立即转为边界说明。",
                "collaborative",
                "evidence-aware",
                "measured",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "dayu-slot-governance-power-cost",
                        "dayu-slot-methods",
                        "dayu-slot-succession",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "dayu-b-causation",
                        "dayu-b-persona",
                        "dayu-b-teaching-model",
                        "dayu-b-transmitted-distance",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("dayu-p005", "role_voice"),
                ("dayu-p028", "historian_note"),
                ("dayu-p032", "role_voice"),
                ("dayu-p047", "boundary_only"),
            ),
            portrait_asset_key="L101-yi",
        ),
        PersonaProfileBindingV1(
            person_id="person-cef45322",
            persona_kind="composite_group",
            channels=("consult", "scenario"),
            voice=_voice(
                "collective_first_person",
                "以多聚落合成视角追问风险、粮食和保护是否公平，不声称代表所有居民。",
                "collective",
                "fairness-focused",
                "questioning",
            ),
            focus_answer_slot_ids=(
                "dayu-slot-governance-power-cost",
                "dayu-slot-methods",
            ),
            boundary_ids=("dayu-b-persona", "dayu-b-teaching-model"),
            evidence_uses=_evidence(
                ("dayu-p028", "role_voice"),
                ("dayu-p047", "boundary_only"),
            ),
            portrait_asset_key="L101-settlement-representative",
        ),
        PersonaProfileBindingV1(
            person_id="person-dc224fcf",
            persona_kind="composite_group",
            channels=("consult", "scenario"),
            voice=_voice(
                "collective_first_person",
                "以合成劳动群体视角说明轮换、口粮和安全代价，不虚构工具、伤亡或统计。",
                "collective",
                "plain",
                "safety-focused",
            ),
            focus_answer_slot_ids=(
                "dayu-slot-governance-power-cost",
                "dayu-slot-methods",
            ),
            boundary_ids=("dayu-b-persona", "dayu-b-teaching-model"),
            evidence_uses=_evidence(
                ("dayu-p028", "role_voice"),
                ("dayu-p047", "boundary_only"),
            ),
            portrait_asset_key="L101-flood-worker",
        ),
    )
    bindings = (
        _binding("dayu-voice-01-survey", "survey-waterways", "person-31118bee"),
        _binding("dayu-voice-02-divert", "dredge-diversion", "person-7c4825d9"),
        _binding(
            "dayu-voice-03-reinforce",
            "reinforce-settlements",
            "person-cef45322",
        ),
        _binding("dayu-voice-04-rotate", "rotate-labor", "person-dc224fcf"),
        _binding("dayu-voice-05-share", "share-map-plan", "person-31118bee"),
        _binding(
            "dayu-voice-06-grain",
            "release-emergency-grain",
            "person-cef45322",
        ),
        _binding(
            "dayu-voice-07-dikes",
            "force-emergency-dikes",
            "person-dc224fcf",
        ),
    )
    provisional = PersonaPackV1(
        pack_id="dayu-persona-pack",
        course_id="C-prequin-state",
        lesson_id="L101",
        pack_version=1,
        course_content_version=1,
        course_checksum=DAYU_COURSE_CHECKSUM,
        scenario_id="dayu-crisis-governance",
        scenario_version=1,
        scenario_checksum=DAYU_SCENARIO_CHECKSUM,
        evidence_corpus_id="dayu-evidence",
        evidence_version=2,
        evidence_checksum=DAYU_EVIDENCE_CHECKSUM,
        profiles=tuple(sorted(profiles, key=lambda item: item.person_id)),
        scenario_voice_bindings=tuple(
            sorted(bindings, key=lambda item: item.binding_id)
        ),
        created_at=DAYU_PERSONA_CREATED_AT,
        sealed_at=sealed_at,
        sealed_by=sealed_by,
        checksum="0" * 64,
    )
    return sign_persona_pack(provisional)


__all__ = [
    "DAYU_COURSE_CHECKSUM",
    "DAYU_EVIDENCE_CHECKSUM",
    "DAYU_PERSONA_CREATED_AT",
    "DAYU_SCENARIO_CHECKSUM",
    "build_dayu_persona_pack_v1",
]
