from __future__ import annotations

from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from services.contracts.v1 import Checksum, ContractId
from services.contracts.learning_v1 import canonical_checksum


class ClassroomTaskRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    client_task_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=4000)
    status: Literal["open", "closed"] = "open"
    expected_checksum: Checksum | None = None


class ClassroomTaskV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["classroom-task/v1"] = "classroom-task/v1"
    task_id: ContractId
    client_task_id: ContractId
    course_id: ContractId
    lesson_id: ContractId
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=4000)
    status: Literal["open", "closed"]
    teacher_id: str = Field(min_length=2, max_length=64)
    teacher_display_name: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=1)
    teacher_text_checksum: Checksum
    created_at: AwareDatetime
    updated_at: AwareDatetime
    checksum: Checksum

    @model_validator(mode="after")
    def integrity(self):
        if self.checksum != canonical_checksum(self.model_dump(mode="json", exclude={"checksum"})):
            raise ValueError("classroom task checksum mismatch")
        return self


class LearningRubricV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    facts: Literal["not_assessed", "needs_revision", "developing", "supported"]
    evidence: Literal["not_assessed", "needs_revision", "developing", "supported"]
    explanation: Literal["not_assessed", "needs_revision", "developing", "supported"]
