"""Sealed persona bindings for the L103 flagship lesson.

Only stable IDs and speaking policy live here. Historical prose remains in the
course and EvidenceCorpusV2 artifacts bound by checksum.
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

SHANGYANG_PERSONA_CREATED_AT = datetime(2026, 8, 31, 7, 35, tzinfo=timezone.utc)
SHANGYANG_COURSE_CHECKSUM = (
    "149560ce57cd86b4f12ee75293f62dca27b9f0e15242b568b1a19c9338f6536f"
)
SHANGYANG_SCENARIO_CHECKSUM = (
    "eddb9370bc7ad0cd8080784c68f15db25ecba11ffed4f2d272e8588d10f87cbd"
)
SHANGYANG_EVIDENCE_CHECKSUM = (
    "73658c57df6ca4323a13b3305021608d5a4aa59351129927a9eeaa769c20fdfc"
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
    node_id: str,
    action_id: str,
    person_id: str,
) -> ScenarioVoiceBindingV1:
    return ScenarioVoiceBindingV1(
        binding_id=binding_id,
        node_id=node_id,
        action_id=action_id,
        person_id=person_id,
    )


def build_shangyang_persona_pack_v1(
    *,
    sealed_at: datetime = SHANGYANG_PERSONA_CREATED_AT,
    sealed_by: str = "chronovita-content-team",
) -> PersonaPackV1:
    """Build the deterministic six-profile L103 persona pack."""

    shangyang = "person-c797c18e"
    duke_xiao = "person-bd001399"
    aristocrats = "person-75b468fa"
    households = "person-a748c58d"
    soldiers = "person-44990ad0"
    officials = "person-829de766"

    profiles = (
        PersonaProfileBindingV1(
            person_id=shangyang,
            persona_kind="historical_person",
            channels=("consult", "scenario"),
            voice=_voice(
                "first_person_limited",
                "强调规则、信用和执行条件；只借审校后的传世记忆表达，不把后世文本冒充原话。",
                "decisive",
                "evidence-aware",
                "procedural",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "shangyang-slot-01-overview",
                        "shangyang-slot-02-identity",
                        "shangyang-slot-04-moving-wood",
                        "shangyang-slot-11-fangsheng",
                        "shangyang-slot-13-book-of-lord-shang",
                        "shangyang-slot-15-evaluation",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "shangyang-boundary-01-transmitted-distance",
                        "shangyang-boundary-03-fangsheng-claim",
                        "shangyang-boundary-04-slips-distance",
                        "shangyang-boundary-05-shangjunshu-authorship",
                        "shangyang-boundary-06-modern-rule-of-law",
                        "shangyang-boundary-07-multi-causation",
                        "shangyang-boundary-09-persona-hindsight",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("shangyang-p003", "role_voice"),
                ("shangyang-p005", "role_voice"),
                ("shangyang-p012", "historian_note"),
                ("shangyang-p016", "boundary_only"),
                ("shangyang-p018", "historian_note"),
                ("shangyang-p020", "boundary_only"),
                ("shangyang-p024", "historian_note"),
                ("shangyang-p048", "boundary_only"),
            ),
            portrait_asset_key="L103-shang-yang",
        ),
        PersonaProfileBindingV1(
            person_id=duke_xiao,
            persona_kind="historical_person",
            channels=("consult", "scenario"),
            voice=_voice(
                "first_person_limited",
                "从求变窗口、支持联盟和政策延续谈取舍，不虚构密谈，也不预言统一必然发生。",
                "decisive",
                "political",
                "strategic",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "shangyang-slot-01-overview",
                        "shangyang-slot-02-identity",
                        "shangyang-slot-03-chronology",
                        "shangyang-slot-10-death-and-legacy",
                        "shangyang-slot-15-evaluation",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "shangyang-boundary-01-transmitted-distance",
                        "shangyang-boundary-02-reform-chronology",
                        "shangyang-boundary-07-multi-causation",
                        "shangyang-boundary-09-persona-hindsight",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("shangyang-p003", "role_voice"),
                ("shangyang-p024", "historian_note"),
                ("shangyang-p025", "role_voice"),
                ("shangyang-p032", "historian_note"),
                ("shangyang-p037", "boundary_only"),
                ("shangyang-p043", "historian_note"),
            ),
            portrait_asset_key="L103-duke-xiao",
        ),
        PersonaProfileBindingV1(
            person_id=aristocrats,
            persona_kind="composite_group",
            channels=("consult", "scenario"),
            voice=_voice(
                "collective_first_person",
                "以旧身份秩序中的合成群体追问程序、权力和利益变化，不假装所有贵族立场一致。",
                "collective",
                "critical",
                "status-aware",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "shangyang-slot-05-military-merit",
                        "shangyang-slot-10-death-and-legacy",
                        "shangyang-slot-15-evaluation",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "shangyang-boundary-01-transmitted-distance",
                        "shangyang-boundary-07-multi-causation",
                        "shangyang-boundary-08-teaching-model",
                        "shangyang-boundary-09-persona-hindsight",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("shangyang-p006", "role_voice"),
                ("shangyang-p025", "role_voice"),
                ("shangyang-p036", "historian_note"),
                ("shangyang-p037", "boundary_only"),
                ("shangyang-p043", "historian_note"),
            ),
            portrait_asset_key="L103-hereditary-aristocrat",
        ),
        PersonaProfileBindingV1(
            person_id=households,
            persona_kind="composite_group",
            channels=("consult", "scenario"),
            voice=_voice(
                "collective_first_person",
                "以农耕家庭合成视角衡量收成、征发、连带风险和生活可持续性，不编造税率。",
                "collective",
                "cost-aware",
                "plain",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "shangyang-slot-06-agriculture-war",
                        "shangyang-slot-07-collective-liability",
                        "shangyang-slot-09-land-system",
                        "shangyang-slot-15-evaluation",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "shangyang-boundary-01-transmitted-distance",
                        "shangyang-boundary-04-slips-distance",
                        "shangyang-boundary-08-teaching-model",
                        "shangyang-boundary-09-persona-hindsight",
                        "shangyang-boundary-10-land-concept",
                        "shangyang-boundary-11-unsupported-exact-data",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("shangyang-p007", "role_voice"),
                ("shangyang-p008", "role_voice"),
                ("shangyang-p013", "historian_note"),
                ("shangyang-p017", "boundary_only"),
                ("shangyang-p028", "role_voice"),
                ("shangyang-p036", "historian_note"),
                ("shangyang-p038", "boundary_only"),
                ("shangyang-p041", "historian_note"),
                ("shangyang-p042", "historian_note"),
            ),
            portrait_asset_key="L103-farming-household",
        ),
        PersonaProfileBindingV1(
            person_id=soldiers,
            persona_kind="composite_group",
            channels=("consult", "scenario"),
            voice=_voice(
                "collective_first_person",
                "以军功士卒合成视角并列身份机会与战争风险，不虚构战役、爵级或斩首数字。",
                "collective",
                "direct",
                "risk-aware",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "shangyang-slot-05-military-merit",
                        "shangyang-slot-06-agriculture-war",
                        "shangyang-slot-15-evaluation",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "shangyang-boundary-06-modern-rule-of-law",
                        "shangyang-boundary-07-multi-causation",
                        "shangyang-boundary-08-teaching-model",
                        "shangyang-boundary-09-persona-hindsight",
                        "shangyang-boundary-11-unsupported-exact-data",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("shangyang-p006", "role_voice"),
                ("shangyang-p028", "role_voice"),
                ("shangyang-p036", "historian_note"),
                ("shangyang-p037", "boundary_only"),
                ("shangyang-p038", "boundary_only"),
            ),
            portrait_asset_key="L103-merit-soldier",
        ),
        PersonaProfileBindingV1(
            person_id=officials,
            persona_kind="composite_group",
            channels=("consult", "scenario"),
            voice=_voice(
                "collective_first_person",
                "以基层吏员合成视角要求规则可登记、可复核、可执行，并明确较晚秦简的年代距离。",
                "administrative",
                "collective",
                "procedural",
            ),
            focus_answer_slot_ids=tuple(
                sorted(
                    (
                        "shangyang-slot-07-collective-liability",
                        "shangyang-slot-08-county-administration",
                        "shangyang-slot-12-sleeping-tiger-slips",
                        "shangyang-slot-13-book-of-lord-shang",
                        "shangyang-slot-15-evaluation",
                    )
                )
            ),
            boundary_ids=tuple(
                sorted(
                    (
                        "shangyang-boundary-01-transmitted-distance",
                        "shangyang-boundary-02-reform-chronology",
                        "shangyang-boundary-04-slips-distance",
                        "shangyang-boundary-05-shangjunshu-authorship",
                        "shangyang-boundary-06-modern-rule-of-law",
                        "shangyang-boundary-08-teaching-model",
                        "shangyang-boundary-09-persona-hindsight",
                    )
                )
            ),
            evidence_uses=_evidence(
                ("shangyang-p008", "role_voice"),
                ("shangyang-p009", "role_voice"),
                ("shangyang-p015", "boundary_only"),
                ("shangyang-p016", "boundary_only"),
                ("shangyang-p017", "boundary_only"),
                ("shangyang-p019", "historian_note"),
                ("shangyang-p028", "role_voice"),
                ("shangyang-p033", "boundary_only"),
                ("shangyang-p040", "boundary_only"),
            ),
            portrait_asset_key="L103-county-clerk",
        ),
    )

    bindings = (
        _binding(
            "shangyang-voice-01-consult",
            "court-debate",
            "consult-interests",
            aristocrats,
        ),
        _binding(
            "shangyang-voice-02-announce",
            "court-debate",
            "announce-reform-goal",
            duke_xiao,
        ),
        _binding(
            "shangyang-voice-03-silence",
            "court-debate",
            "silence-opposition",
            aristocrats,
        ),
        _binding(
            "shangyang-voice-04-publish",
            "law-publication",
            "publish-clear-rules",
            officials,
        ),
        _binding(
            "shangyang-voice-05-promise",
            "law-publication",
            "stage-symbolic-promise",
            shangyang,
        ),
        _binding(
            "shangyang-voice-06-liability",
            "law-publication",
            "impose-collective-liability",
            households,
        ),
        _binding(
            "shangyang-voice-07-balance",
            "incentive-design",
            "balance-farming-and-merit",
            households,
        ),
        _binding(
            "shangyang-voice-08-merit",
            "incentive-design",
            "prioritize-military-merit",
            soldiers,
        ),
        _binding(
            "shangyang-voice-09-farming",
            "incentive-design",
            "reward-farming-first",
            households,
        ),
        _binding(
            "shangyang-voice-10-measures",
            "administration",
            "standardize-measures",
            officials,
        ),
        _binding(
            "shangyang-voice-11-county",
            "administration",
            "build-county-offices",
            officials,
        ),
        _binding(
            "shangyang-voice-12-requisition",
            "administration",
            "rapid-requisition-network",
            households,
        ),
        _binding(
            "shangyang-voice-13-defer",
            "administration",
            "defer-local-implementation",
            duke_xiao,
        ),
        _binding(
            "shangyang-voice-14-audit", "enforcement", "phase-and-audit", officials
        ),
        _binding(
            "shangyang-voice-15-penalties",
            "enforcement",
            "enforce-with-severe-penalties",
            households,
        ),
        _binding(
            "shangyang-voice-16-correct", "enforcement", "correct-burdens", households
        ),
        _binding(
            "shangyang-voice-17-suspend",
            "enforcement",
            "suspend-enforcement",
            aristocrats,
        ),
        _binding(
            "shangyang-voice-18-consolidate",
            "evaluation",
            "consolidate-balanced-reform",
            shangyang,
        ),
        _binding(
            "shangyang-voice-19-mobilize", "evaluation", "drive-mobilization", soldiers
        ),
        _binding(
            "shangyang-voice-20-negotiate",
            "evaluation",
            "negotiate-limited-reform",
            duke_xiao,
        ),
        _binding(
            "shangyang-voice-21-abandon", "evaluation", "abandon-reform", aristocrats
        ),
    )

    provisional = PersonaPackV1(
        pack_id="shangyang-persona-pack",
        course_id="C-prequin-state",
        lesson_id="L103",
        pack_version=2,
        course_content_version=1,
        course_checksum=SHANGYANG_COURSE_CHECKSUM,
        scenario_id="shangyang-institutional-reform",
        scenario_version=1,
        scenario_checksum=SHANGYANG_SCENARIO_CHECKSUM,
        evidence_corpus_id="shangyang-evidence",
        evidence_version=3,
        evidence_checksum=SHANGYANG_EVIDENCE_CHECKSUM,
        profiles=tuple(sorted(profiles, key=lambda item: item.person_id)),
        scenario_voice_bindings=tuple(
            sorted(bindings, key=lambda item: item.binding_id)
        ),
        created_at=SHANGYANG_PERSONA_CREATED_AT,
        sealed_at=sealed_at,
        sealed_by=sealed_by,
        checksum="0" * 64,
    )
    return sign_persona_pack(provisional)


__all__ = [
    "SHANGYANG_COURSE_CHECKSUM",
    "SHANGYANG_EVIDENCE_CHECKSUM",
    "SHANGYANG_PERSONA_CREATED_AT",
    "SHANGYANG_SCENARIO_CHECKSUM",
    "build_shangyang_persona_pack_v1",
]
