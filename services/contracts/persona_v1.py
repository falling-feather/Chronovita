from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from services.contracts.v1 import Checksum, ContractId, NonEmptyText

PersonaChannel = Literal["consult", "scenario"]
PersonaKind = Literal["historical_person", "transmitted_memory", "composite_group"]
EvidenceUseMode = Literal["role_voice", "historian_note", "boundary_only"]
VoiceRegister = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
ToneTag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
]


class PersonaContractModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        revalidate_instances="always",
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )


class PersonaVoiceV1(PersonaContractModel):
    perspective: Literal[
        "first_person_limited",
        "collective_first_person",
        "third_person_facilitator",
    ]
    speech_register: VoiceRegister = Field(alias="register")
    tone_tags: tuple[ToneTag, ...] = Field(min_length=1, max_length=8)
    length_policy: Literal["brief", "standard", "expanded"] = "standard"

    @model_validator(mode="after")
    def validate_voice(self) -> "PersonaVoiceV1":
        _require_sorted_unique(self.tone_tags, "voice tone_tags")
        return self


class PersonaPolicyV1(PersonaContractModel):
    afterlife_material_policy: Literal["historian_note_only"] = "historian_note_only"
    unknown_policy: Literal["explicit_insufficient"] = "explicit_insufficient"
    disclaimer_code: Literal["role_expression_not_source_quote"] = (
        "role_expression_not_source_quote"
    )


class PersonaEvidenceUseV1(PersonaContractModel):
    passage_id: ContractId
    mode: EvidenceUseMode


class PersonaProfileBindingV1(PersonaContractModel):
    person_id: ContractId
    persona_kind: PersonaKind
    channels: tuple[PersonaChannel, ...] = Field(min_length=1)
    voice: PersonaVoiceV1
    policy: PersonaPolicyV1 = Field(default_factory=PersonaPolicyV1)
    focus_answer_slot_ids: tuple[ContractId, ...] = Field(min_length=1)
    boundary_ids: tuple[ContractId, ...] = Field(min_length=1)
    evidence_uses: tuple[PersonaEvidenceUseV1, ...] = Field(min_length=1)
    portrait_asset_key: ContractId | None = None

    @model_validator(mode="after")
    def validate_profile(self) -> "PersonaProfileBindingV1":
        _require_sorted_unique(self.channels, "profile channels")
        _require_sorted_unique(
            self.focus_answer_slot_ids,
            "profile focus_answer_slot_ids",
        )
        _require_sorted_unique(self.boundary_ids, "profile boundary_ids")
        _require_sorted_unique(
            [item.passage_id for item in self.evidence_uses],
            "profile evidence passage_ids",
        )
        if not any(item.mode == "role_voice" for item in self.evidence_uses):
            raise ValueError("persona profiles require at least one role_voice passage")
        return self


class ScenarioVoiceBindingV1(PersonaContractModel):
    binding_id: ContractId
    node_id: ContractId = Field(
        description=(
            "Pinned scenario node_id; rules_v1 scenarios without explicit nodes use "
            "the reserved global-rule-set route namespace."
        )
    )
    action_id: ContractId
    person_id: ContractId


class PersonaPackV1(PersonaContractModel):
    schema_version: Literal["persona-pack/v1"] = "persona-pack/v1"
    pack_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    pack_version: int = Field(ge=1)
    status: Literal["sealed"] = "sealed"
    course_content_version: int = Field(ge=1)
    course_checksum: Checksum
    scenario_id: ContractId
    scenario_version: int = Field(ge=1)
    scenario_checksum: Checksum
    evidence_corpus_id: ContractId
    evidence_version: int = Field(ge=1)
    evidence_checksum: Checksum
    profiles: tuple[PersonaProfileBindingV1, ...] = Field(min_length=1)
    scenario_voice_bindings: tuple[ScenarioVoiceBindingV1, ...] = ()
    created_at: AwareDatetime
    sealed_at: AwareDatetime
    sealed_by: NonEmptyText
    checksum: Checksum

    @model_validator(mode="after")
    def validate_pack(self) -> "PersonaPackV1":
        _require_sorted_unique(
            [item.person_id for item in self.profiles],
            "persona profiles",
        )
        _require_sorted_unique(
            [item.binding_id for item in self.scenario_voice_bindings],
            "scenario voice bindings",
        )

        profile_channels = {
            item.person_id: set(item.channels) for item in self.profiles
        }
        seen_routes: set[tuple[str, str]] = set()
        for binding in self.scenario_voice_bindings:
            channels = profile_channels.get(binding.person_id)
            if channels is None:
                raise ValueError(
                    f"scenario voice binding {binding.binding_id} references an unknown profile"
                )
            if "scenario" not in channels:
                raise ValueError(
                    f"scenario voice binding {binding.binding_id} requires the scenario channel"
                )
            route = (binding.node_id, binding.action_id)
            if route in seen_routes:
                raise ValueError(
                    "scenario voice bindings must be unique by node_id and action_id"
                )
            seen_routes.add(route)

        if self.sealed_at < self.created_at:
            raise ValueError("sealed_at cannot precede created_at")
        return self


def calculate_persona_checksum(payload: BaseModel) -> str:
    if not isinstance(payload, BaseModel):
        raise TypeError(
            "validate raw data with its Pydantic contract before calculating a checksum"
        )
    data = payload.model_dump(mode="json")
    if "checksum" not in data:
        raise ValueError("persona contract does not expose a top-level checksum field")
    data["checksum"] = None
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sign_persona_pack(payload: PersonaPackV1) -> PersonaPackV1:
    data = payload.model_dump(mode="json")
    data["checksum"] = calculate_persona_checksum(payload)
    return PersonaPackV1.model_validate(data)


def verify_persona_checksum(payload: BaseModel) -> bool:
    checksum = getattr(payload, "checksum", None)
    return isinstance(checksum, str) and checksum == calculate_persona_checksum(payload)


def persona_schema_document(model: type[BaseModel], schema_id: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "$comment": (
            "Pydantic semantic validation additionally enforces immutable sealed packs, "
            "stable reference ordering, least-privilege role voice evidence and unique "
            "scenario speaker routes. Cross-artifact references are validated by the "
            "publication workflow."
        ),
        **model.model_json_schema(ref_template="#/$defs/{model}"),
    }


PERSONA_SCHEMA_DOCUMENTS: dict[str, tuple[type[BaseModel], str]] = {
    "persona-pack.schema.json": (
        PersonaPackV1,
        "https://chronovita.local/schemas/persona/v1/persona-pack.schema.json",
    ),
}


def _require_sorted_unique(values, label: str) -> None:
    normalized = list(values)
    if normalized != sorted(set(normalized)):
        raise ValueError(f"{label} must be unique and sorted")


__all__ = [
    "EvidenceUseMode",
    "PERSONA_SCHEMA_DOCUMENTS",
    "PersonaChannel",
    "PersonaContractModel",
    "PersonaEvidenceUseV1",
    "PersonaKind",
    "PersonaPackV1",
    "PersonaPolicyV1",
    "PersonaProfileBindingV1",
    "PersonaVoiceV1",
    "ScenarioVoiceBindingV1",
    "calculate_persona_checksum",
    "persona_schema_document",
    "sign_persona_pack",
    "verify_persona_checksum",
]
