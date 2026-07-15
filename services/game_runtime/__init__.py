from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat as stat_module
from typing import Literal, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from services.contracts.rules_v1 import (
    RuleActionUnavailable,
    RuleEvaluationError,
    UnknownRuleAction,
    available_rule_action_ids,
    evaluate_rule_action,
    initial_rule_snapshot,
    render_rule_narrative,
    rule_snapshot_from_session,
    select_rule_ending_id,
)
from services.contracts.v1 import (
    ActionClassificationEvidenceV1,
    ContractId,
    CoursePackageV1,
    GameSessionV1,
    NarrativeEvidenceV1,
    NarrativeMessageV1,
    NpcChangeV1,
    NpcStateV1,
    ObservedEntityV1,
    PlayerInput,
    RuntimeBundleV1,
    ScenarioTemplateV1,
    StateChangeV1,
    TurnV1,
    calculate_action_classification_basis_checksum,
    calculate_narrative_basis_checksum,
    calculate_text_checksum,
    reviewed_narrative_refs,
    verify_contract_checksum,
)


ENGINE_VERSION = "rules-v1.0.0"
MAX_CONTRACT_FILE_BYTES = 2 * 1024 * 1024


class GameRuntimeError(ValueError):
    code = "game_runtime_error"


class ScenarioFileError(GameRuntimeError):
    code = "scenario_file_error"


class ScenarioIntegrityError(GameRuntimeError):
    code = "scenario_integrity_error"


class SessionIntegrityError(GameRuntimeError):
    code = "session_integrity_error"


class SessionTerminalError(GameRuntimeError):
    code = "session_terminal"


class RevisionConflict(GameRuntimeError):
    code = "revision_conflict"


class UnknownAction(GameRuntimeError):
    code = "unknown_action"


class ActionUnavailable(GameRuntimeError):
    code = "action_unavailable"


class DuplicateActionConflict(GameRuntimeError):
    code = "duplicate_action_conflict"


class ScenarioDefinitionError(GameRuntimeError):
    code = "scenario_definition_error"


class RuntimeClassificationContextV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    source: Literal["fixed", "exact", "llm"]
    reason_code: Literal["fixed_action", "exact_match", "semantic_match"]
    policy_version: Literal["action-classifier/v1"] = "action-classifier/v1"
    reviewed_fact_refs: list[ContractId] = Field(default_factory=list)
    provider: str = Field(default="", max_length=32)
    model: str = Field(default="", max_length=128)
    output_checksum: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_context(self) -> "RuntimeClassificationContextV1":
        if len(set(self.reviewed_fact_refs)) != len(self.reviewed_fact_refs):
            raise ValueError("reviewed_fact_refs must be unique")
        expected_reason = {
            "fixed": "fixed_action",
            "exact": "exact_match",
            "llm": "semantic_match",
        }[self.source]
        if self.reason_code != expected_reason:
            raise ValueError("classification context source and reason_code are inconsistent")
        if self.source == "llm":
            if not self.reviewed_fact_refs:
                raise ValueError("llm classification context requires reviewed facts")
            if not self.provider or not self.model or not self.output_checksum:
                raise ValueError("llm classification context requires model metadata")
        elif (
            self.reviewed_fact_refs
            or self.provider
            or self.model
            or self.output_checksum
        ):
            raise ValueError("non-llm classification context cannot claim model evidence")
        return self


class RuntimeCommandV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    client_action_id: ContractId
    raw_input: PlayerInput
    action_id: ContractId | None = None
    action_source: Literal["fixed", "free_input", "fallback"] = "fixed"
    classification_confidence: float | None = Field(default=None, ge=0, le=1)
    classification_context: RuntimeClassificationContextV1 | None = None
    expected_revision: int = Field(ge=1)
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def validate_classification(self) -> "RuntimeCommandV1":
        if self.action_source != "fixed" and self.action_id is None:
            raise ValueError("free_input and fallback commands require a classified action_id")
        if self.classification_context is not None:
            if self.action_source == "fixed" and self.classification_context.source != "fixed":
                raise ValueError("fixed commands require fixed classification context")
            if self.action_source == "free_input" and self.classification_context.source == "fixed":
                raise ValueError("free input cannot claim fixed classification context")
            if self.action_source == "fallback":
                raise ValueError("fallback commands cannot carry typed classification context")
        return self


class AvailableActionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: ContractId
    label: str
    description: str = ""


class AdvanceResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session: GameSessionV1
    turn: TurnV1
    action_feedback: str = ""
    triggered_event_ids: tuple[ContractId, ...] = ()
    ending_id: ContractId | None = None


ModelT = TypeVar("ModelT", bound=BaseModel)


def load_contract_file(path: str | Path, model: type[ModelT]) -> ModelT:
    source = Path(path)
    try:
        with source.open("rb") as handle:
            opened_stat = os.fstat(handle.fileno())
            if not stat_module.S_ISREG(opened_stat.st_mode):
                raise ScenarioFileError(
                    f"contract path is not a regular file: {source}"
                )
            if opened_stat.st_size > MAX_CONTRACT_FILE_BYTES:
                raise ScenarioFileError(
                    f"contract file exceeds {MAX_CONTRACT_FILE_BYTES} bytes: {source}"
                )
            raw = handle.read(MAX_CONTRACT_FILE_BYTES + 1)
            path_stat = os.lstat(source)
            if stat_module.S_ISLNK(path_stat.st_mode):
                raise ScenarioFileError(
                    f"contract file cannot be a symbolic link: {source}"
                )
            if not os.path.samestat(opened_stat, path_stat):
                raise ScenarioFileError(
                    f"contract file changed while being read: {source}"
                )
        if len(raw) > MAX_CONTRACT_FILE_BYTES:
            raise ScenarioFileError(
                f"contract file exceeds {MAX_CONTRACT_FILE_BYTES} bytes: {source}"
            )
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except ScenarioFileError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioFileError(f"cannot read contract file {source}: {exc}") from exc
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ScenarioFileError(f"invalid {model.__name__} file {source}: {exc}") from exc


def load_course_package(path: str | Path) -> CoursePackageV1:
    course = load_contract_file(path, CoursePackageV1)
    if course.status != "sealed" or not verify_contract_checksum(course):
        raise ScenarioIntegrityError("course package must be sealed with a valid checksum")
    return course


def load_scenario_template(path: str | Path) -> ScenarioTemplateV1:
    scenario = load_contract_file(path, ScenarioTemplateV1)
    if scenario.status != "sealed" or not verify_contract_checksum(scenario):
        raise ScenarioIntegrityError("scenario template must be sealed with a valid checksum")
    return scenario


class SituationEngineV1:
    """Pure, deterministic ScenarioTemplate V1 session runtime."""

    def __init__(
        self,
        course: CoursePackageV1,
        scenario: ScenarioTemplateV1,
    ) -> None:
        try:
            bundle = RuntimeBundleV1.model_validate(
                {
                    "course": course.model_dump(mode="json"),
                    "scenario": scenario.model_dump(mode="json"),
                }
            )
        except ValidationError as exc:
            raise ScenarioIntegrityError(
                f"course and scenario cannot form a runtime bundle: {exc}"
            ) from exc
        self.course = bundle.course
        self.scenario = bundle.scenario
        self._actions = {
            item.action_id: item
            for item in self.scenario.action_rules
        }
        self._events = {
            item.event_id: item
            for item in self.scenario.event_rules
        }
        self._endings = {
            item.ending_id: item
            for item in self.scenario.ending_rules
        }
        self._alias_index = self._build_alias_index()

    @classmethod
    def from_files(
        cls,
        course_path: str | Path,
        scenario_path: str | Path,
    ) -> "SituationEngineV1":
        return cls(
            load_course_package(course_path),
            load_scenario_template(scenario_path),
        )

    @property
    def ruleset_hash(self) -> str:
        return str(self.scenario.checksum)

    def start_session(
        self,
        *,
        session_id: str,
        user_id: str,
        started_at: AwareDatetime,
        random_seed: str = "",
        ai_evidence_version: Literal[0, 1] = 0,
    ) -> GameSessionV1:
        snapshot = initial_rule_snapshot(self.scenario)
        ending_id = select_rule_ending_id(self.scenario, snapshot, 0)
        available_ids = (
            available_rule_action_ids(self.scenario, snapshot, 1)
            if ending_id is None
            else ()
        )
        if ending_id is not None:
            status = "completed"
            terminal_reason = None
        elif not available_ids:
            status = "failed"
            terminal_reason = "no_available_actions_at_start"
        else:
            status = "active"
            terminal_reason = None

        flags = {}
        if terminal_reason is not None:
            flags["rules_terminal_reason"] = terminal_reason
        ending = self._endings.get(ending_id) if ending_id else None
        session = GameSessionV1(
            session_id=session_id,
            user_id=user_id,
            course_id=self.course.course_id,
            lesson_id=self.course.lesson_id,
            scenario_id=self.scenario.scenario_id,
            scenario_version=self.scenario.scenario_version,
            course_content_version=self.course.content_version,
            course_checksum=str(self.course.checksum),
            scenario_checksum=str(self.scenario.checksum),
            engine_version=ENGINE_VERSION,
            ai_evidence_version=ai_evidence_version,
            random_seed=random_seed,
            status=status,
            revision=1,
            current_turn=0,
            current_state=snapshot.state_dict(),
            current_node_id=snapshot.current_node_id,
            npc_states=[
                NpcStateV1(
                    person_id=item.person_id,
                    attitude=item.attitude,
                    trust=item.trust,
                    last_basis_refs=list(spec.fact_refs),
                    updated_turn=0,
                )
                for item, spec in zip(snapshot.npcs, self.scenario.npcs)
            ],
            available_action_ids=list(available_ids),
            available_choices=self._labels_for(available_ids),
            summary=ending.summary if ending is not None else "",
            flags=flags,
            history=[
                NarrativeMessageV1(
                    role="system",
                    text=self.scenario.opening,
                    turn_no=0,
                )
            ],
            ending_id=ending_id,
            started_at=started_at,
            updated_at=started_at,
            ended_at=started_at if status != "active" else None,
        )
        return self._validated_session(session)

    def available_actions(self, session: GameSessionV1) -> tuple[AvailableActionV1, ...]:
        checked = self._validated_session(session)
        return tuple(
            AvailableActionV1(
                action_id=action_id,
                label=self._actions[action_id].label,
                description=self._actions[action_id].description,
            )
            for action_id in checked.available_action_ids
        )

    def resolve_action_id(self, raw_input: str, action_id: str | None = None) -> str:
        if action_id is not None:
            if action_id not in self._actions:
                raise UnknownAction(f"unknown action {action_id}")
            return action_id
        resolved = self._alias_index.get(_normalize_action_text(raw_input))
        if resolved is None:
            raise UnknownAction("fixed input does not match an action id, label or alias")
        return resolved

    def apply_action(
        self,
        session: GameSessionV1,
        command: RuntimeCommandV1,
    ) -> AdvanceResultV1:
        checked = self._validated_session(session)
        action_id = self.resolve_action_id(command.raw_input, command.action_id)

        existing = next(
            (
                turn
                for turn in checked.turns
                if turn.client_action_id == command.client_action_id
            ),
            None,
        )
        if existing is not None:
            if self._command_matches_turn(command, action_id, existing):
                action = self._actions[existing.classified_action_id]
                return AdvanceResultV1(
                    session=checked,
                    turn=existing,
                    action_feedback=action.feedback,
                    triggered_event_ids=tuple(existing.triggered_event_ids),
                    ending_id=checked.ending_id,
                )
            raise DuplicateActionConflict(
                f"client_action_id {command.client_action_id} was already used"
            )

        if command.expected_revision != checked.revision:
            raise RevisionConflict(
                f"expected revision {command.expected_revision}, current revision is {checked.revision}"
            )
        if checked.status != "active":
            raise SessionTerminalError(
                f"session {checked.session_id} is already {checked.status}"
            )
        if command.occurred_at < checked.updated_at:
            raise SessionIntegrityError("command time cannot be earlier than session updated_at")

        turn_no = checked.current_turn + 1
        snapshot = rule_snapshot_from_session(self.scenario, checked)
        try:
            evaluated = evaluate_rule_action(
                self.scenario,
                snapshot,
                action_id,
                turn_no,
            )
        except UnknownRuleAction as exc:
            raise UnknownAction(str(exc)) from exc
        except RuleActionUnavailable as exc:
            raise ActionUnavailable(str(exc)) from exc
        except RuleEvaluationError as exc:
            raise SessionIntegrityError(str(exc)) from exc

        narrative = render_rule_narrative(self.scenario, evaluated)
        confidence = (
            command.classification_confidence
            if command.classification_confidence is not None
            else (1.0 if command.action_source == "fixed" else None)
        )
        classification_evidence = None
        narrative_evidence = None
        if checked.ai_evidence_version == 1:
            classification_context = self._classification_context_for(
                command,
                action_id,
            )
            if confidence is None:
                raise SessionIntegrityError(
                    "evidence-version-1 commands require classification confidence"
                )
            available_before = available_rule_action_ids(
                self.scenario,
                snapshot,
                turn_no,
            )
            classification_evidence = ActionClassificationEvidenceV1(
                source=classification_context.source,
                reason_code=classification_context.reason_code,
                policy_version=classification_context.policy_version,
                available_action_ids=list(available_before),
                reviewed_fact_refs=list(classification_context.reviewed_fact_refs),
                basis_checksum=calculate_action_classification_basis_checksum(
                    course_checksum=str(self.course.checksum),
                    scenario_checksum=str(self.scenario.checksum),
                    session_id=checked.session_id,
                    revision=turn_no,
                    snapshot=snapshot,
                    raw_input=command.raw_input,
                    available_action_ids=available_before,
                    reviewed_fact_refs=classification_context.reviewed_fact_refs,
                    action_id=action_id,
                    confidence=confidence,
                    source=classification_context.source,
                    reason_code=classification_context.reason_code,
                    policy_version=classification_context.policy_version,
                ),
                provider=classification_context.provider,
                model=classification_context.model,
                output_checksum=classification_context.output_checksum,
            )
            allowed_fact_refs, allowed_source_ref_ids = reviewed_narrative_refs(
                self.course,
                self.scenario,
                action_id=action_id,
                triggered_event_ids=evaluated.triggered_event_ids,
                ending_id=evaluated.ending_id,
            )
            narrative_evidence = NarrativeEvidenceV1(
                source="rules",
                policy_version="rule-narrative/v1",
                basis_checksum=calculate_narrative_basis_checksum(
                    course_checksum=str(self.course.checksum),
                    scenario_checksum=str(self.scenario.checksum),
                    session_id=checked.session_id,
                    turn_no=turn_no,
                    classification_evidence=classification_evidence,
                    action_feedback=self._actions[action_id].feedback,
                    snapshot_before=snapshot,
                    result=evaluated,
                    rule_narrative=narrative,
                    allowed_fact_refs=allowed_fact_refs,
                    allowed_source_ref_ids=allowed_source_ref_ids,
                ),
                output_checksum=calculate_text_checksum(narrative),
                allowed_fact_refs=allowed_fact_refs,
                allowed_source_ref_ids=allowed_source_ref_ids,
            )
        turn = TurnV1(
            turn_id=_derived_id("turn", checked.session_id, command.client_action_id),
            session_id=checked.session_id,
            client_action_id=command.client_action_id,
            turn_no=turn_no,
            status="applied",
            raw_input=command.raw_input,
            action_source=command.action_source,
            classified_action_id=action_id,
            classification_confidence=confidence,
            state_before=snapshot.state_dict(),
            state_after=evaluated.snapshot.state_dict(),
            state_changes=[
                StateChangeV1(
                    variable_id=item.variable_id,
                    before=item.before,
                    after=item.after,
                    delta=item.delta,
                )
                for item in evaluated.state_changes
            ],
            npc_changes=[
                NpcChangeV1(
                    person_id=item.person_id,
                    attitude_before=item.attitude_before,
                    attitude_after=item.attitude_after,
                    trust_before=item.trust_before,
                    trust_after=item.trust_after,
                    revealed_fact_refs=list(item.revealed_fact_refs),
                )
                for item in evaluated.npc_changes
            ],
            triggered_event_ids=list(evaluated.triggered_event_ids),
            fact_refs=list(evaluated.fact_refs),
            narrative=narrative,
            narrative_source="rules",
            classification_evidence=classification_evidence,
            narrative_evidence=narrative_evidence,
            ruleset_hash=self.ruleset_hash,
            created_at=command.occurred_at,
        )

        if evaluated.ending_id is not None:
            status = "completed"
            terminal_reason = None
        elif evaluated.turn_limit_reached:
            status = "failed"
            terminal_reason = "max_turns_without_ending"
        elif not evaluated.available_action_ids:
            status = "failed"
            terminal_reason = "no_available_actions"
        else:
            status = "active"
            terminal_reason = None

        flags = dict(checked.flags)
        flags.pop("rules_terminal_reason", None)
        if terminal_reason is not None:
            flags["rules_terminal_reason"] = terminal_reason
        ending = self._endings.get(evaluated.ending_id) if evaluated.ending_id else None
        payload = checked.model_dump(mode="python")
        payload.update(
            status=status,
            revision=checked.revision + 1,
            current_turn=turn_no,
            current_state=evaluated.snapshot.state_dict(),
            current_node_id=evaluated.snapshot.current_node_id,
            npc_states=self._updated_npc_states(checked, evaluated),
            turns=[*checked.turns, turn],
            triggered_event_ids=list(evaluated.snapshot.triggered_event_ids),
            available_action_ids=(
                list(evaluated.available_action_ids) if status == "active" else []
            ),
            available_choices=(
                self._labels_for(evaluated.available_action_ids)
                if status == "active"
                else []
            ),
            summary=(ending.summary if ending is not None else narrative),
            flags=flags,
            observed_entities=self._updated_observed_entities(
                checked,
                evaluated.triggered_event_ids,
                turn_no,
            ),
            history=[
                *checked.history,
                NarrativeMessageV1(role="player", text=command.raw_input, turn_no=turn_no),
                NarrativeMessageV1(role="narrator", text=narrative, turn_no=turn_no),
            ],
            ending_id=evaluated.ending_id,
            dossier_id=None,
            updated_at=command.occurred_at,
            ended_at=command.occurred_at if status != "active" else None,
        )
        try:
            next_session = GameSessionV1.model_validate(payload)
        except ValidationError as exc:
            raise SessionIntegrityError(f"generated session is invalid: {exc}") from exc
        next_session = self._validated_session(next_session)
        return AdvanceResultV1(
            session=next_session,
            turn=turn,
            action_feedback=self._actions[action_id].feedback,
            triggered_event_ids=evaluated.triggered_event_ids,
            ending_id=evaluated.ending_id,
        )

    def replay(
        self,
        *,
        session_id: str,
        user_id: str,
        started_at: AwareDatetime,
        commands: tuple[RuntimeCommandV1, ...] | list[RuntimeCommandV1],
        random_seed: str = "",
    ) -> GameSessionV1:
        session = self.start_session(
            session_id=session_id,
            user_id=user_id,
            started_at=started_at,
            random_seed=random_seed,
        )
        for command in commands:
            session = self.apply_action(session, command).session
        return session

    def _validated_session(self, session: GameSessionV1) -> GameSessionV1:
        try:
            bundle = RuntimeBundleV1.model_validate(
                {
                    "course": self.course.model_dump(mode="json"),
                    "scenario": self.scenario.model_dump(mode="json"),
                    "session": session.model_dump(mode="json"),
                }
            )
        except ValidationError as exc:
            raise SessionIntegrityError(f"session does not match its pinned ruleset: {exc}") from exc
        if bundle.session is None:
            raise SessionIntegrityError("runtime bundle lost its session")
        return bundle.session

    def _build_alias_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for action in self.scenario.action_rules:
            for value in (action.action_id, action.label, *action.aliases):
                key = _normalize_action_text(value)
                existing = index.get(key)
                if existing is not None and existing != action.action_id:
                    raise ScenarioDefinitionError(
                        f"ambiguous action label or alias {value!r}: {existing}, {action.action_id}"
                    )
                index[key] = action.action_id
        return index

    def _labels_for(self, action_ids) -> list[str]:
        return [self._actions[action_id].label for action_id in action_ids]

    def _updated_npc_states(self, session: GameSessionV1, evaluated) -> list[NpcStateV1]:
        previous = {item.person_id: item for item in session.npc_states}
        changed = {item.person_id for item in evaluated.npc_changes}
        basis = list(evaluated.fact_refs)
        return [
            NpcStateV1(
                person_id=item.person_id,
                attitude=item.attitude,
                trust=item.trust,
                known_fact_refs=list(item.known_fact_refs),
                last_basis_refs=(
                    basis if item.person_id in changed and basis else previous[item.person_id].last_basis_refs
                ),
                flags=dict(previous[item.person_id].flags),
                updated_turn=item.updated_turn,
            )
            for item in evaluated.snapshot.npcs
        ]

    def _updated_observed_entities(
        self,
        session: GameSessionV1,
        event_ids,
        turn_no: int,
    ) -> list[ObservedEntityV1]:
        observed = list(session.observed_entities)
        existing = {item.entity_id for item in observed}
        for event_id in event_ids:
            entity_id = _derived_id("event", self.scenario.scenario_id, event_id)
            if entity_id in existing:
                continue
            event = self._events[event_id]
            observed.append(
                ObservedEntityV1(
                    entity_id=entity_id,
                    name=event.title,
                    kind="event",
                    description=event.narrative,
                    first_seen_turn=turn_no,
                )
            )
            existing.add(entity_id)
        return observed

    def _classification_context_for(
        self,
        command: RuntimeCommandV1,
        action_id: str,
    ) -> RuntimeClassificationContextV1:
        context = command.classification_context
        if context is None:
            if command.action_source == "fixed":
                context = RuntimeClassificationContextV1(
                    source="fixed",
                    reason_code="fixed_action",
                )
            elif command.action_source == "free_input":
                try:
                    exact_action_id = self.resolve_action_id(command.raw_input)
                except UnknownAction:
                    exact_action_id = None
                if exact_action_id != action_id:
                    raise SessionIntegrityError(
                        "semantic free input requires server classification evidence"
                    )
                context = RuntimeClassificationContextV1(
                    source="exact",
                    reason_code="exact_match",
                )
            else:
                raise SessionIntegrityError(
                    "evidence-version-1 sessions do not accept fallback commands"
                )
        if context.source == "fixed":
            if command.action_source != "fixed" or command.classification_confidence not in {
                None,
                1.0,
            }:
                raise SessionIntegrityError("fixed classification evidence requires confidence 1")
        elif context.source == "exact":
            if (
                command.action_source != "free_input"
                or command.classification_confidence != 1.0
            ):
                raise SessionIntegrityError("exact classification evidence requires confidence 1")
        elif (
            command.action_source != "free_input"
            or command.classification_confidence is None
        ):
            raise SessionIntegrityError("llm classification evidence requires confidence")
        return context

    @staticmethod
    def _command_matches_turn(
        command: RuntimeCommandV1,
        action_id: str,
        turn: TurnV1,
    ) -> bool:
        confidence = (
            command.classification_confidence
            if command.classification_confidence is not None
            else (1.0 if command.action_source == "fixed" else None)
        )
        return (
            command.expected_revision == turn.turn_no
            and turn.raw_input == command.raw_input
            and turn.action_source == command.action_source
            and turn.classified_action_id == action_id
            and turn.classification_confidence == confidence
        )


def _normalize_action_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _derived_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScenarioFileError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


__all__ = [
    "ActionUnavailable",
    "AdvanceResultV1",
    "AvailableActionV1",
    "DuplicateActionConflict",
    "ENGINE_VERSION",
    "GameRuntimeError",
    "RevisionConflict",
    "RuntimeClassificationContextV1",
    "RuntimeCommandV1",
    "ScenarioDefinitionError",
    "ScenarioFileError",
    "ScenarioIntegrityError",
    "SessionIntegrityError",
    "SessionTerminalError",
    "SituationEngineV1",
    "UnknownAction",
    "load_contract_file",
    "load_course_package",
    "load_scenario_template",
]
