import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine, update
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.contracts.examples import build_dayu_bundle
from services.contracts.v1 import (
    DossierV1,
    GameSessionV1,
    RuntimeBundleV1,
    calculate_contract_checksum,
)
from services.game_runtime import SessionIntegrityError
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.service import GameRuntimeService
from services.game_runtime.store import GameRuntimeStore, game_sessions_table


BASE_TIME = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)


class ExplodingClassifier:
    def __init__(self):
        self.calls = 0

    async def classify(self, engine, session, raw_input):
        self.calls += 1
        raise AssertionError("offline replay must not call the classifier")


class GameEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.database = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(self.database.dispose)
        self.repository = ScenarioCatalogRepository(
            content_root=REPO_ROOT / "content",
            catalog_path=REPO_ROOT
            / "content"
            / "scenarios"
            / "catalog.v1.json",
        )
        self.classifier = ExplodingClassifier()
        self.store = GameRuntimeStore(self.database)
        self.service = GameRuntimeService(
            self.repository,
            self.store,
            self.classifier,
        )

    def test_new_service_turn_has_typed_fixed_and_rules_evidence(self):
        session = self._start("evidence-shape")
        result = self.service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-evidence-001",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        )

        self.assertEqual(result.session.ai_evidence_version, 1)
        self.assertEqual(result.turn.classification_evidence.source, "fixed")
        self.assertEqual(
            result.turn.classification_evidence.reason_code,
            "fixed_action",
        )
        self.assertEqual(result.turn.narrative_evidence.source, "rules")
        self.assertEqual(result.turn.narrative_source, "rules")
        self.assertEqual(result.turn.narrative_metadata, {})
        self._bundle(result.session)

    def test_basis_output_history_and_summary_tampering_fail_closed(self):
        session = self._start("evidence-tamper")
        session = self.service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-evidence-002",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        ).session
        raw = session.model_dump(mode="json")

        classification_basis = _clone(raw)
        classification_basis["turns"][0]["classification_evidence"][
            "basis_checksum"
        ] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "classification basis checksum"):
            self._bundle(GameSessionV1.model_validate(classification_basis))

        narrative_output = _clone(raw)
        narrative_output["turns"][0]["narrative_evidence"][
            "output_checksum"
        ] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "narrative output checksum"):
            self._bundle(GameSessionV1.model_validate(narrative_output))

        history = _clone(raw)
        history["history"][-1]["text"] = "tampered narrator projection"
        with self.assertRaisesRegex(ValidationError, "session history"):
            self._bundle(GameSessionV1.model_validate(history))

        summary = _clone(raw)
        summary["summary"] = "tampered summary"
        with self.assertRaisesRegex(ValidationError, "session summary"):
            self._bundle(GameSessionV1.model_validate(summary))

    def test_missing_new_evidence_and_legacy_non_rule_narration_are_rejected(self):
        session = self._start("evidence-required")
        session = self.service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-evidence-003",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        ).session
        missing = session.model_dump(mode="json")
        missing["turns"][0]["classification_evidence"] = None
        with self.assertRaisesRegex(ValidationError, "require typed evidence"):
            GameSessionV1.model_validate(missing)

        legacy = build_dayu_bundle().session.model_dump(mode="json")
        legacy["turns"][0]["narrative_source"] = "llm"
        with self.assertRaisesRegex(ValidationError, "evidence-version-0"):
            GameSessionV1.model_validate(legacy)

    def test_recomputed_outer_envelope_cannot_hide_evidence_tampering(self):
        session = self._start("outer-envelope")
        session = self.service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-evidence-004",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        ).session
        record = self.store.load_session(session.session_id)
        envelope = json.loads(record.raw_data)
        envelope["session"]["turns"][0]["classification_evidence"][
            "basis_checksum"
        ] = "0" * 64
        envelope["checksum"] = _v2_session_checksum(
            envelope["session"],
            envelope.get("release_identity"),
        )
        with self.database.begin() as connection:
            connection.execute(
                update(game_sessions_table)
                .where(game_sessions_table.c.session_id == session.session_id)
                .values(data=_canonical_json(envelope))
            )

        with self.assertRaisesRegex(SessionIntegrityError, "classification basis checksum"):
            self.service.get_session(session.session_id)

    def test_dossier_consequence_must_quote_the_persisted_turn(self):
        session = self._start("dossier-evidence")
        for revision, action_id in enumerate(
            (
                "survey-terrain",
                "explain-plan",
                "open-channels",
                "allocate-food",
                "open-channels",
            ),
            start=1,
        ):
            session = self.service.apply_fixed_action(
                session.session_id,
                client_action_id=f"fixed-dossier-{revision:03d}",
                action_id=action_id,
                expected_revision=revision,
                occurred_at=BASE_TIME + timedelta(minutes=revision),
            ).session
        dossier = self.service.get_dossier(session.session_id)
        raw = dossier.model_dump(mode="json")
        raw["key_choices"][0]["consequence"] = "tampered consequence"
        raw["checksum"] = "0" * 64
        draft = DossierV1.model_validate(raw)
        raw["checksum"] = calculate_contract_checksum(draft)
        tampered = DossierV1.model_validate(raw)

        with self.assertRaisesRegex(ValidationError, "consequence"):
            self._bundle(session, tampered)

    def test_offline_replay_reuses_verified_session_without_classifier(self):
        session = self._start("offline-replay")
        session = self.service.apply_fixed_action(
            session.session_id,
            client_action_id="fixed-evidence-005",
            action_id="survey-terrain",
            expected_revision=1,
            occurred_at=BASE_TIME + timedelta(minutes=1),
        ).session

        replay = self.service.replay_session(session.session_id)

        self.assertEqual(replay.session, session)
        self.assertEqual(len(replay.commands), 1)
        self.assertEqual(self.classifier.calls, 0)

    def _start(self, suffix: str):
        return self.service.start_session(
            "scenario-dayu-flood-control",
            user_id=f"student-{suffix}",
            client_request_id=f"request-{suffix}",
            now=BASE_TIME,
        )[1]

    def _bundle(self, session: GameSessionV1, dossier: DossierV1 | None = None):
        engine = self.repository.get_exact(
            session.scenario_id,
            session.scenario_version,
            str(session.scenario_checksum),
            course_id=session.course_id,
            lesson_id=session.lesson_id,
            course_content_version=session.course_content_version,
            course_checksum=str(session.course_checksum),
        )
        return RuntimeBundleV1(
            course=engine.course,
            scenario=engine.scenario,
            session=session,
            dossier=dossier,
        )


def _clone(payload: dict) -> dict:
    return json.loads(_canonical_json(payload))


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _v2_session_checksum(
    session_payload: dict,
    release_identity: dict | None,
) -> str:
    payload: object = session_payload
    if release_identity is not None:
        payload = {
            "session": session_payload,
            "release_identity": release_identity,
        }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
