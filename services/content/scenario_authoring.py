from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from services import content as content_data
from services.content import runtime_artifacts
from services.contracts.v1 import (
    CompatibilitySourceV1,
    ContractId,
    ScenarioTemplateV1,
    calculate_contract_checksum,
)

_WRITE_LOCK = RLock()
_CONTRACT_ID_ADAPTER = TypeAdapter(ContractId)


class ScenarioAuthoringModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        str_strip_whitespace=True,
    )


class ScenarioDraftVariableV1(ScenarioAuthoringModel):
    variable_id: str = ""
    label: str = ""
    description: str = ""
    initial: float = 50
    minimum: float = 0
    maximum: float = 100


class ScenarioDraftNpcV1(ScenarioAuthoringModel):
    person_id: str = ""
    display_name: str = ""
    role: str = ""
    persona: str = ""
    boundaries: list[str] = Field(default_factory=list)
    initial_attitude: float = 0
    initial_trust: float = 0
    fact_refs: list[str] = Field(default_factory=list)


class ScenarioDraftConditionV1(ScenarioAuthoringModel):
    kind: Literal["state", "turn", "npc"] = "state"
    variable_id: str = ""
    person_id: str = ""
    field: Literal["attitude", "trust"] = "attitude"
    operator: Literal["lt", "lte", "eq", "gte", "gt"] = "gte"
    value: float = 0

    def contract_payload(self) -> dict[str, object]:
        if self.kind == "state":
            return {
                "kind": "state",
                "variable_id": self.variable_id,
                "operator": self.operator,
                "value": self.value,
            }
        if self.kind == "npc":
            return {
                "kind": "npc",
                "person_id": self.person_id,
                "field": self.field,
                "operator": self.operator,
                "value": self.value,
            }
        return {
            "kind": "turn",
            "operator": self.operator,
            "value": self.value,
        }


class ScenarioDraftEffectV1(ScenarioAuthoringModel):
    kind: Literal["state", "npc"] = "state"
    variable_id: str = ""
    person_id: str = ""
    operation: Literal["add", "set"] = "add"
    value: float = 0
    attitude_delta: float = 0
    trust_delta: float = 0
    reveal_fact_refs: list[str] = Field(default_factory=list)

    def contract_payload(self) -> dict[str, object]:
        if self.kind == "npc":
            return {
                "kind": "npc",
                "person_id": self.person_id,
                "attitude_delta": self.attitude_delta,
                "trust_delta": self.trust_delta,
                "reveal_fact_refs": self.reveal_fact_refs,
            }
        return {
            "kind": "state",
            "variable_id": self.variable_id,
            "operation": self.operation,
            "value": self.value,
        }


class ScenarioDraftActionV1(ScenarioAuthoringModel):
    action_id: str = ""
    label: str = ""
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    available_when: list[ScenarioDraftConditionV1] = Field(default_factory=list)
    effects: list[ScenarioDraftEffectV1] = Field(default_factory=list)
    feedback: str = ""
    fact_refs: list[str] = Field(default_factory=list)
    next_node_id: str | None = None

    def contract_payload(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "label": self.label,
            "description": self.description,
            "aliases": self.aliases,
            "available_when": [item.contract_payload() for item in self.available_when],
            "effects": [item.contract_payload() for item in self.effects],
            "feedback": self.feedback,
            "fact_refs": self.fact_refs,
            "next_node_id": self.next_node_id,
        }


class ScenarioDraftEventV1(ScenarioAuthoringModel):
    event_id: str = ""
    title: str = ""
    match: Literal["all", "any"] = "all"
    trigger: list[ScenarioDraftConditionV1] = Field(default_factory=list)
    effects: list[ScenarioDraftEffectV1] = Field(default_factory=list)
    narrative: str = ""
    once: bool = True
    priority: int = 100
    fact_refs: list[str] = Field(default_factory=list)

    def contract_payload(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "match": self.match,
            "trigger": [item.contract_payload() for item in self.trigger],
            "effects": [item.contract_payload() for item in self.effects],
            "narrative": self.narrative,
            "once": self.once,
            "priority": self.priority,
            "fact_refs": self.fact_refs,
        }


class ScenarioDraftEndingV1(ScenarioAuthoringModel):
    ending_id: str = ""
    title: str = ""
    match: Literal["all", "any"] = "all"
    conditions: list[ScenarioDraftConditionV1] = Field(default_factory=list)
    summary: str = ""
    historical_explanation: str = ""
    major_costs: list[str] = Field(default_factory=list)
    source_ref_ids: list[str] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list)
    priority: int = 100

    def contract_payload(self) -> dict[str, object]:
        return {
            "ending_id": self.ending_id,
            "title": self.title,
            "match": self.match,
            "conditions": [item.contract_payload() for item in self.conditions],
            "summary": self.summary,
            "historical_explanation": self.historical_explanation,
            "major_costs": self.major_costs,
            "source_ref_ids": self.source_ref_ids,
            "fact_refs": self.fact_refs,
            "priority": self.priority,
        }


class ScenarioDraftNodeV1(ScenarioAuthoringModel):
    node_id: str = ""
    title: str = ""
    narration: str = ""
    action_ids: list[str] = Field(default_factory=list)
    ending_id: str | None = None


class ScenarioDraftDossierV1(ScenarioAuthoringModel):
    title_template: str = "《{scenario_title}卷宗》"
    reflection_questions: list[str] = Field(default_factory=list)
    knowledge_node_kinds: list[str] = Field(default_factory=list)


class ScenarioAuthorDraftV1(ScenarioAuthoringModel):
    schema_version: Literal["scenario-author-draft/v1"] = "scenario-author-draft/v1"
    scenario_id: ContractId
    course_id: str = ""
    lesson_id: str = ""
    title: str = ""
    scenario_type: Literal["crisis_governance", "institutional_reform", "council"] = (
        "crisis_governance"
    )
    student_role: str = ""
    objective: str = ""
    opening: str = ""
    max_turns: int = Field(default=6, ge=1, le=50)
    variables: list[ScenarioDraftVariableV1] = Field(default_factory=list)
    npcs: list[ScenarioDraftNpcV1] = Field(default_factory=list)
    action_rules: list[ScenarioDraftActionV1] = Field(default_factory=list)
    event_rules: list[ScenarioDraftEventV1] = Field(default_factory=list)
    ending_rules: list[ScenarioDraftEndingV1] = Field(default_factory=list)
    start_node_id: str | None = None
    nodes: list[ScenarioDraftNodeV1] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list)
    source_ref_ids: list[str] = Field(default_factory=list)
    dossier_template: ScenarioDraftDossierV1 = Field(default_factory=ScenarioDraftDossierV1)
    compatibility: CompatibilitySourceV1 = Field(default_factory=CompatibilitySourceV1)
    revision: int = Field(default=0, ge=0)
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def contract_content(self) -> dict[str, object]:
        return {
            "schema_version": "scenario-template/v1",
            "engine_family": "rules_v1",
            "scenario_id": self.scenario_id,
            "course_id": self.course_id,
            "lesson_id": self.lesson_id,
            "title": self.title,
            "scenario_type": self.scenario_type,
            "student_role": self.student_role,
            "objective": self.objective,
            "opening": self.opening,
            "max_turns": self.max_turns,
            "variables": [item.model_dump(mode="json") for item in self.variables],
            "npcs": [item.model_dump(mode="json") for item in self.npcs],
            "action_rules": [item.contract_payload() for item in self.action_rules],
            "event_rules": [item.contract_payload() for item in self.event_rules],
            "ending_rules": [item.contract_payload() for item in self.ending_rules],
            "start_node_id": self.start_node_id,
            "nodes": [item.model_dump(mode="json") for item in self.nodes],
            "fact_refs": self.fact_refs,
            "source_ref_ids": self.source_ref_ids,
            "dossier_template": self.dossier_template.model_dump(mode="json"),
            "compatibility": self.compatibility.model_dump(mode="json"),
        }


class ScenarioDraftRecordV1(ScenarioAuthoringModel):
    scenario_id: ContractId
    course_id: str
    lesson_id: str
    title: str
    scenario_type: str
    revision: int
    updated_at: AwareDatetime | None
    updated_by: str | None


class ScenarioDraftValidationIssueV1(ScenarioAuthoringModel):
    path: str
    code: str
    message: str


class ScenarioDraftValidationReportV1(ScenarioAuthoringModel):
    valid: bool
    issues: list[ScenarioDraftValidationIssueV1] = Field(default_factory=list)
    variable_count: int = 0
    npc_count: int = 0
    action_count: int = 0
    event_count: int = 0
    ending_count: int = 0


class ScenarioDraftConflict(RuntimeError):
    code = "scenario_draft_conflict"


class ScenarioDraftValidationFailed(ValueError):
    code = "scenario_draft_invalid"

    def __init__(self, report: ScenarioDraftValidationReportV1):
        super().__init__("Scenario draft is not ready to seal.")
        self.report = report


def scenario_draft_template() -> ScenarioAuthorDraftV1:
    return ScenarioAuthorDraftV1(
        scenario_id="scenario-new",
        course_id="C-course-id",
        lesson_id="lesson-id",
        title="历史抉择局",
        student_role="本课历史情境中的决策者",
        objective="通过取舍推动局势，并说明每次选择的依据与代价。",
        opening="教师在这里交代学生进入关卡时面对的局势。",
        variables=[
            ScenarioDraftVariableV1(
                variable_id="progress",
                label="推进度",
                description="方案完成或局势推进的程度。",
                initial=20,
            )
        ],
        action_rules=[
            ScenarioDraftActionV1(
                action_id="advance-carefully",
                label="稳步推进",
                description="选择一项可以逐步推动局势的行动。",
                effects=[
                    ScenarioDraftEffectV1(
                        variable_id="progress",
                        operation="add",
                        value=20,
                    )
                ],
                feedback="局势发生变化，学生需要继续观察代价。",
            )
        ],
        ending_rules=[
            ScenarioDraftEndingV1(
                ending_id="ending-progress",
                title="阶段目标达成",
                conditions=[
                    ScenarioDraftConditionV1(
                        variable_id="progress",
                        operator="gte",
                        value=60,
                    )
                ],
                summary="学生完成了阶段目标；正式历史解释由教师填写。",
                priority=10,
            ),
            ScenarioDraftEndingV1(
                ending_id="ending-turn-limit",
                title="进入复盘",
                conditions=[
                    ScenarioDraftConditionV1(
                        kind="turn",
                        operator="gte",
                        value=6,
                    )
                ],
                summary="达到回合上限，进入课堂复盘。",
                priority=1000,
            ),
        ],
        dossier_template=ScenarioDraftDossierV1(
            reflection_questions=["哪一次选择最关键？依据和代价分别是什么？"],
            knowledge_node_kinds=["cause", "consequence", "concept"],
        ),
    )


def save_scenario_draft(
    payload: ScenarioAuthorDraftV1,
    *,
    saved_by: str,
) -> ScenarioAuthorDraftV1:
    content_data.ensure_content_dirs()
    with _WRITE_LOCK:
        existing = get_scenario_draft(payload.scenario_id)
        if existing is not None and payload.revision != existing.revision:
            raise ScenarioDraftConflict(
                f"Scenario draft revision changed: expected {payload.revision}, "
                f"current {existing.revision}."
            )
        if existing is None and payload.revision != 0:
            raise ScenarioDraftConflict(
                f"New scenario draft must start at revision 0, got {payload.revision}."
            )
        now = _now()
        data = payload.model_copy(deep=True)
        data.revision = (existing.revision + 1) if existing else 1
        data.created_at = existing.created_at if existing else (data.created_at or now)
        data.updated_at = now
        data.created_by = existing.created_by if existing else saved_by
        data.updated_by = saved_by
        data = ScenarioAuthorDraftV1.model_validate(data.model_dump(mode="json"))
        content_data._atomic_write_json(
            _scenario_draft_path(data.scenario_id),
            data.model_dump(mode="json"),
        )
        return data


def get_scenario_draft(scenario_id: str) -> ScenarioAuthorDraftV1 | None:
    path = _scenario_draft_path(scenario_id)
    if not path.exists() and not path.is_symlink():
        return None
    return _read_scenario_draft(path)


def list_scenario_drafts() -> list[ScenarioDraftRecordV1]:
    content_data.ensure_content_dirs()
    records = [
        _draft_record(_read_scenario_draft(path))
        for path in sorted(content_data.scenario_draft_dir().glob("*.json"))
    ]
    return sorted(records, key=lambda item: (item.updated_at or _epoch(), item.scenario_id), reverse=True)


def validate_scenario_draft(
    draft: ScenarioAuthorDraftV1,
) -> ScenarioDraftValidationReportV1:
    if len(draft.title.strip()) > 160:
        return _validation_report(
            draft,
            valid=False,
            issues=[
                ScenarioDraftValidationIssueV1(
                    path="title",
                    code="string_too_long",
                    message="关卡标题不能超过 160 个字符。",
                )
            ],
        )
    try:
        _sealed_contract(draft, version=1, sealed_by="validation", sealed_at=_now())
    except ValidationError as exc:
        issues = [
            ScenarioDraftValidationIssueV1(
                path=".".join(str(part) for part in item["loc"]) or "$",
                code=str(item["type"]),
                message=str(item["msg"]),
            )
            for item in exc.errors(include_url=False)
        ]
        return _validation_report(draft, valid=False, issues=issues)
    return _validation_report(draft, valid=True, issues=[])


def validate_saved_scenario_draft(scenario_id: str) -> ScenarioDraftValidationReportV1:
    draft = get_scenario_draft(scenario_id)
    if draft is None:
        raise FileNotFoundError(f"Scenario draft not found: {scenario_id}")
    return validate_scenario_draft(draft)


def seal_scenario_draft(
    scenario_id: str,
    *,
    sealed_by: str,
) -> tuple[ScenarioTemplateV1, runtime_artifacts.RuntimeScenarioRecord, bool]:
    with _WRITE_LOCK:
        draft = get_scenario_draft(scenario_id)
        if draft is None:
            raise FileNotFoundError(f"Scenario draft not found: {scenario_id}")
        report = validate_scenario_draft(draft)
        if not report.valid:
            raise ScenarioDraftValidationFailed(report)

        matching = runtime_artifacts.list_staged_scenarios(scenario_id=scenario_id)
        for item in matching:
            if (item.descriptor.course_id, item.descriptor.lesson_id) != (
                draft.course_id,
                draft.lesson_id,
            ):
                raise ScenarioDraftConflict(
                    "A scenario_id cannot move to another course or lesson after sealing."
                )
        latest = max(matching, key=lambda item: item.descriptor.version, default=None)
        if latest is not None:
            previous, _ = runtime_artifacts.load_staged_scenario(
                course_id=latest.descriptor.course_id,
                lesson_id=latest.descriptor.lesson_id,
                scenario_id=latest.descriptor.artifact_id,
                scenario_version=latest.descriptor.version,
                scenario_checksum=latest.descriptor.checksum,
            )
            if _scenario_content_fingerprint(previous) == _draft_content_fingerprint(draft):
                return previous, latest, True

        version = (latest.descriptor.version + 1) if latest else 1
        sealed = _sealed_contract(
            draft,
            version=version,
            sealed_by=sealed_by,
            sealed_at=_now(),
        )
        record = runtime_artifacts.stage_scenario(sealed)
        return sealed, record, False


def _sealed_contract(
    draft: ScenarioAuthorDraftV1,
    *,
    version: int,
    sealed_by: str,
    sealed_at: datetime,
) -> ScenarioTemplateV1:
    data = draft.contract_content()
    data.update(
        {
            "scenario_version": version,
            "status": "sealed",
            "created_at": draft.created_at or sealed_at,
            "updated_at": sealed_at,
            "sealed_at": sealed_at,
            "sealed_by": sealed_by,
            "checksum": "0" * 64,
        }
    )
    provisional = ScenarioTemplateV1.model_validate(data)
    data["checksum"] = calculate_contract_checksum(provisional)
    return ScenarioTemplateV1.model_validate(data)


def _validation_report(
    draft: ScenarioAuthorDraftV1,
    *,
    valid: bool,
    issues: list[ScenarioDraftValidationIssueV1],
) -> ScenarioDraftValidationReportV1:
    return ScenarioDraftValidationReportV1(
        valid=valid,
        issues=issues,
        variable_count=len(draft.variables),
        npc_count=len(draft.npcs),
        action_count=len(draft.action_rules),
        event_count=len(draft.event_rules),
        ending_count=len(draft.ending_rules),
    )


def _read_scenario_draft(path: Path) -> ScenarioAuthorDraftV1:
    if path.is_symlink() or not path.is_file():
        raise content_data.ContentIntegrityError(
            f"Scenario draft must be a regular file: {path}"
        )
    try:
        draft = ScenarioAuthorDraftV1.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise content_data.ContentIntegrityError(
            f"Cannot read scenario draft: {path}"
        ) from exc
    if path != _scenario_draft_path(draft.scenario_id):
        raise content_data.ContentIntegrityError(
            f"Scenario draft identity does not match its path: {path}"
        )
    return draft


def _draft_record(draft: ScenarioAuthorDraftV1) -> ScenarioDraftRecordV1:
    return ScenarioDraftRecordV1(
        scenario_id=draft.scenario_id,
        course_id=draft.course_id,
        lesson_id=draft.lesson_id,
        title=draft.title,
        scenario_type=draft.scenario_type,
        revision=draft.revision,
        updated_at=draft.updated_at,
        updated_by=draft.updated_by,
    )


def _draft_content_fingerprint(draft: ScenarioAuthorDraftV1) -> str:
    normalized = _sealed_contract(
        draft,
        version=1,
        sealed_by="fingerprint",
        sealed_at=_epoch(),
    )
    return _scenario_content_fingerprint(normalized)


def _scenario_content_fingerprint(scenario: ScenarioTemplateV1) -> str:
    data = scenario.model_dump(mode="json")
    for field in (
        "scenario_version",
        "status",
        "created_at",
        "updated_at",
        "sealed_at",
        "sealed_by",
        "checksum",
    ):
        data.pop(field, None)
    return _fingerprint(data)


def _fingerprint(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _scenario_draft_path(scenario_id: str) -> Path:
    validated = _CONTRACT_ID_ADAPTER.validate_python(scenario_id)
    return content_data.scenario_draft_dir() / f"{validated}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _epoch() -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


__all__ = [
    "ScenarioAuthorDraftV1",
    "ScenarioDraftConflict",
    "ScenarioDraftRecordV1",
    "ScenarioDraftValidationFailed",
    "ScenarioDraftValidationReportV1",
    "get_scenario_draft",
    "list_scenario_drafts",
    "save_scenario_draft",
    "scenario_draft_template",
    "seal_scenario_draft",
    "validate_saved_scenario_draft",
    "validate_scenario_draft",
]
