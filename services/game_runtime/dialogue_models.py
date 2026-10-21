from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from services.contracts.v1 import Checksum, ContractId

DialogueText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=900),
]
DialogueRouteSource = Literal["local_state", "external_api", "fallback"]
DialogueRouteReason = Literal[
    "fixed_action_local",
    "free_input_local",
    "classified_fallback_local",
    "free_input_external_polish",
    "external_unavailable",
    "external_invalid_response",
    "external_reference_out_of_bounds",
]
DialogueFallbackReason = Literal[
    "",
    "provider_unavailable",
    "invalid_response",
    "reference_out_of_bounds",
]


class _DialogueModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


class ScenarioDialogueReleaseIdentityV1(_DialogueModel):
    """The immutable V5 release identity pinned by a game session."""

    release_id: ContractId
    release_no: int = Field(ge=1)
    release_checksum: Checksum


class ScenarioDialogueModelOutputV1(_DialogueModel):
    """The complete writable surface exposed to an optional external model.

    The model cannot return state, events, choices, an ending, a speaker or any
    release identity.  It may only polish the already-settled local line and
    select evidence passages from the server-provided allowlist.
    """

    text: DialogueText
    # JSON model responses use arrays; strict tuple validation rejected valid
    # grounded dialogue completions before provenance checks could run.
    used_passage_ids: list[ContractId] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_passage_ids(self) -> "ScenarioDialogueModelOutputV1":
        _require_sorted_unique(self.used_passage_ids, "model used_passage_ids")
        return self


class ScenarioDialogueExternalCompletionV1(_DialogueModel):
    """Server-owned provenance wrapped around the model's constrained output."""

    output: ScenarioDialogueModelOutputV1
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)


class ScenarioNpcDialogueV1(_DialogueModel):
    """Auditable, non-authoritative NPC dialogue projection for one settled turn."""

    schema_version: Literal["scenario-npc-dialogue/v1"] = "scenario-npc-dialogue/v1"
    session_id: ContractId
    turn_id: ContractId
    turn_no: int = Field(ge=1)
    node_id: ContractId
    action_id: ContractId
    binding_id: ContractId

    person_id: ContractId
    display_name: str = Field(min_length=1, max_length=120)
    role: str = Field(max_length=240)
    persona_kind: Literal[
        "historical_person",
        "transmitted_memory",
        "composite_group",
    ]
    portrait_asset_key: ContractId | None = None
    text: DialogueText
    disclaimer: Literal["角色化教学表达，不是史料原话。"] = (
        "角色化教学表达，不是史料原话。"
    )

    route_source: DialogueRouteSource
    route_reason: DialogueRouteReason

    release_id: ContractId
    release_no: int = Field(ge=1)
    release_checksum: Checksum
    course_id: ContractId
    lesson_id: ContractId
    course_content_version: int = Field(ge=1)
    course_checksum: Checksum
    scenario_id: ContractId
    scenario_version: int = Field(ge=1)
    scenario_checksum: Checksum
    persona_pack_id: ContractId
    persona_pack_version: int = Field(ge=1)
    persona_pack_checksum: Checksum
    evidence_corpus_id: ContractId
    evidence_version: int = Field(ge=1)
    evidence_checksum: Checksum

    used_passage_ids: tuple[ContractId, ...] = Field(min_length=1, max_length=3)
    used_slot_ids: tuple[ContractId, ...] = Field(default_factory=tuple, max_length=16)
    used_boundary_ids: tuple[ContractId, ...] = Field(
        default_factory=tuple,
        min_length=1,
        max_length=16,
    )
    provider: str = Field(default="", max_length=32)
    model: str = Field(default="", max_length=128)
    fallback_reason: DialogueFallbackReason = ""
    basis_checksum: Checksum
    output_checksum: Checksum

    @model_validator(mode="after")
    def validate_projection(self) -> "ScenarioNpcDialogueV1":
        for values, label in (
            (self.used_passage_ids, "used_passage_ids"),
            (self.used_slot_ids, "used_slot_ids"),
            (self.used_boundary_ids, "used_boundary_ids"),
        ):
            _require_sorted_unique(values, label)

        if self.route_source == "external_api":
            if (
                self.route_reason != "free_input_external_polish"
                or not self.provider
                or not self.model
                or self.fallback_reason
            ):
                raise ValueError(
                    "external_api dialogue requires external provenance only"
                )
        elif self.route_source == "local_state":
            if self.route_reason not in {
                "fixed_action_local",
                "free_input_local",
                "classified_fallback_local",
            }:
                raise ValueError("local_state dialogue requires a local route reason")
            if self.provider or self.model or self.fallback_reason:
                raise ValueError(
                    "local_state dialogue cannot claim model or fallback metadata"
                )
        else:
            expected_fallbacks = {
                "external_unavailable": "provider_unavailable",
                "external_invalid_response": "invalid_response",
                "external_reference_out_of_bounds": "reference_out_of_bounds",
            }
            if expected_fallbacks.get(self.route_reason) != self.fallback_reason:
                raise ValueError("fallback route reason and fallback_reason disagree")
            if self.provider or self.model:
                raise ValueError("fallback dialogue cannot claim model provenance")

        if self.output_checksum != dialogue_record_checksum(self):
            raise ValueError("scenario dialogue output checksum is invalid")
        return self


def dialogue_record_checksum(
    payload: ScenarioNpcDialogueV1 | Mapping[str, object],
) -> str:
    """Return the canonical record checksum with ``output_checksum`` nulled."""

    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    elif isinstance(payload, Mapping):
        data = dict(payload)
    else:
        raise TypeError("dialogue checksum requires a model or mapping")
    if "output_checksum" not in data:
        raise ValueError("dialogue record does not expose output_checksum")
    data["output_checksum"] = None
    raw = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_dialogue_record(payload: ScenarioNpcDialogueV1) -> bool:
    try:
        return payload.output_checksum == dialogue_record_checksum(payload)
    except (TypeError, ValueError):
        return False


def _require_sorted_unique(values, label: str) -> None:
    normalized = list(values)
    if normalized != sorted(set(normalized)):
        raise ValueError(f"{label} must be unique and sorted")


__all__ = [
    "DialogueFallbackReason",
    "DialogueRouteReason",
    "DialogueRouteSource",
    "DialogueText",
    "ScenarioDialogueExternalCompletionV1",
    "ScenarioDialogueModelOutputV1",
    "ScenarioDialogueReleaseIdentityV1",
    "ScenarioNpcDialogueV1",
    "dialogue_record_checksum",
    "verify_dialogue_record",
]
