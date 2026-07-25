from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.contracts.v1 import ContractId


ClassifierRejectionReason = Literal[
    "anachronism",
    "fact_conflict",
    "prompt_injection",
    "out_of_scope",
]


class ClassifierModelOutputV1(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=True,
    )

    kind: Literal["matched", "clarification_required", "rejected"]
    action_id: ContractId | None = None
    confidence: float = Field(ge=0, le=1)
    reason_code: Literal[
        "semantic_match",
        "ambiguous",
        "anachronism",
        "fact_conflict",
        "prompt_injection",
        "out_of_scope",
    ]

    @model_validator(mode="after")
    def validate_result_shape(self) -> "ClassifierModelOutputV1":
        if self.kind == "matched":
            if self.action_id is None or self.reason_code != "semantic_match":
                raise ValueError(
                    "matched classification requires action_id and semantic_match"
                )
        elif self.action_id is not None:
            raise ValueError("non-matched classification cannot include action_id")
        elif self.kind == "clarification_required" and self.reason_code != "ambiguous":
            raise ValueError("clarification requires ambiguous reason_code")
        elif self.kind == "rejected" and self.reason_code in {
            "semantic_match",
            "ambiguous",
        }:
            raise ValueError("rejected classification requires a rejection reason")
        return self


ClassificationReason = Literal[
    "exact_match",
    "semantic_match",
    "ambiguous",
    "low_confidence",
    "anachronism",
    "fact_conflict",
    "prompt_injection",
    "out_of_scope",
    "action_unavailable",
    "session_not_active",
    "invalid_input",
    "fact_context_unavailable",
    "invalid_model_action",
    "classifier_context_invalid",
    "provider_unconfigured",
    "provider_timeout",
    "provider_rate_limited",
    "provider_rejected",
    "provider_unavailable",
    "invalid_model_response",
]


class ActionClassificationV1(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal["action-classification/v1"] = "action-classification/v1"
    kind: Literal[
        "matched",
        "clarification_required",
        "rejected",
        "provider_unavailable",
    ]
    source: Literal["exact", "llm", "guardrail", "fallback"]
    reason_code: ClassificationReason
    action_id: ContractId | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    available_action_ids: list[ContractId] = Field(default_factory=list)
    fact_refs: list[ContractId] = Field(default_factory=list)
    prompt_policy_version: Literal["action-classifier/v1"] = "action-classifier/v1"
    provider: str = Field(default="", max_length=32)
    model: str = Field(default="", max_length=128)
    output_checksum: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_authority_boundary(self) -> "ActionClassificationV1":
        available = set(self.available_action_ids)
        if len(available) != len(self.available_action_ids):
            raise ValueError("available_action_ids must be unique")
        if len(set(self.fact_refs)) != len(self.fact_refs):
            raise ValueError("fact_refs must be unique")
        if self.kind == "matched":
            if self.action_id is None or self.action_id not in available:
                raise ValueError("matched action must be currently available")
            if self.confidence is None:
                raise ValueError("matched classification requires confidence")
        elif self.action_id is not None:
            raise ValueError("non-matched classification cannot include action_id")
        if self.source == "exact" and (
            self.kind != "matched" or self.confidence != 1.0
        ):
            raise ValueError("exact source requires a confidence-1 match")
        if self.source == "llm" and (
            self.confidence is None
            or not self.provider
            or not self.model
            or not self.output_checksum
        ):
            raise ValueError(
                "llm source requires confidence, provider, model and output checksum"
            )
        if self.source != "llm" and (self.model or self.output_checksum):
            raise ValueError("non-llm source cannot claim model output metadata")
        allowed_result_shapes = {
            "matched": {
                ("exact", "exact_match"),
                ("llm", "semantic_match"),
            },
            "clarification_required": {
                ("llm", "ambiguous"),
                ("llm", "low_confidence"),
            },
            "rejected": {
                ("guardrail", "action_unavailable"),
                ("guardrail", "session_not_active"),
                ("guardrail", "invalid_input"),
                ("guardrail", "prompt_injection"),
                ("llm", "anachronism"),
                ("llm", "fact_conflict"),
                ("llm", "prompt_injection"),
                ("llm", "out_of_scope"),
            },
            "provider_unavailable": {
                ("fallback", "fact_context_unavailable"),
                ("fallback", "invalid_model_action"),
                ("fallback", "classifier_context_invalid"),
                ("fallback", "provider_unconfigured"),
                ("fallback", "provider_timeout"),
                ("fallback", "provider_rate_limited"),
                ("fallback", "provider_rejected"),
                ("fallback", "provider_unavailable"),
                ("fallback", "invalid_model_response"),
            },
        }
        if (self.source, self.reason_code) not in allowed_result_shapes[self.kind]:
            raise ValueError("classification kind, source and reason_code are inconsistent")
        return self


class NarratorModelOutputV1(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        strict=True,
        str_strip_whitespace=True,
    )

    narrative: str = Field(min_length=1, max_length=1200)
    used_fact_refs: list[ContractId] = Field(default_factory=list, max_length=32)
    used_source_ref_ids: list[ContractId] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_reference_shape(self) -> "NarratorModelOutputV1":
        if len(set(self.used_fact_refs)) != len(self.used_fact_refs):
            raise ValueError("used_fact_refs must be unique")
        if len(set(self.used_source_ref_ids)) != len(self.used_source_ref_ids):
            raise ValueError("used_source_ref_ids must be unique")
        return self
