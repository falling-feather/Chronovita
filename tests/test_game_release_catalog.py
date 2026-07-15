import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from services import content
from services.contracts.examples import (
    build_dayu_bundle,
    build_shangyang_bundle,
)
from services.contracts.release_v2 import (
    ActiveReleasePointerV1,
    CourseReleaseItemV1,
    CourseReleaseItemV2,
    CourseReleaseManifestV1,
    CourseReleaseManifestV2,
    RuntimeArtifactDescriptorV1,
    runtime_artifact_path,
    sign_release_metadata,
)
from services.contracts.v1 import (
    CoursePackageV1,
    RuntimeBundleV1,
    calculate_contract_checksum,
)
from services.game_runtime import ScenarioFileError, ScenarioIntegrityError
from services.game_runtime.catalog import (
    ScenarioCatalogNotFound,
    ScenarioCatalogRepository,
)
from services.game_runtime.service import (
    DuplicateStartConflict,
    GameRuntimeService,
    PublishedScenarioPinRequired,
    ScenarioReleasePinV1,
)
from services.game_runtime.store import GameRuntimeStore


NOW = datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc)
RELEASE_PREFIX = "rel-abcdef0123"


class GameReleaseCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_content_root = content.content_root()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        content.configure(self.root)
        _write_catalog(self.root, [])
        self.repository = _repository(self.root)

    def tearDown(self) -> None:
        content.configure(self.previous_content_root)
        self.temp_dir.cleanup()

    def test_v1_active_release_remains_course_only(self):
        bundle = _runtime_bundle(build_dayu_bundle())
        package_path = "packages/v1/dayu-flood-control-v001.json"
        _write_json(self.root / package_path, bundle.course.model_dump(mode="json"))
        manifest = sign_release_metadata(
            CourseReleaseManifestV1(
                release_id=f"{RELEASE_PREFIX}-0001",
                release_no=1,
                course_id=bundle.course.course_id,
                operation="bootstrap",
                created_at=NOW,
                created_by="release-test",
                items=(
                    CourseReleaseItemV1(
                        lesson_id=bundle.course.lesson_id,
                        course_id=bundle.course.course_id,
                        content_version=bundle.course.content_version,
                        source_path=(
                            f"sealed/{bundle.course.lesson_id}-v001.json"
                        ),
                        source_checksum="1" * 64,
                        package_path=package_path,
                        package_checksum=str(bundle.course.checksum),
                    ),
                ),
                checksum="0" * 64,
            )
        )
        _write_manifest(self.root, manifest)
        _activate(self.root, manifest, generation=1, previous_release_id=None)

        self.assertEqual(self.repository.list_active_records(), ())

    def test_active_v2_merges_published_and_static_development_bundles(self):
        development = _runtime_bundle(build_shangyang_bundle())
        development_entry = _write_static_bundle(
            self.root,
            development,
            name="shangyang",
        )
        _write_catalog(self.root, [development_entry])

        published = _runtime_bundle(build_dayu_bundle())
        manifest = _build_v2_manifest(published, release_no=1)
        _write_v2_release(self.root, manifest, published)
        _activate(self.root, manifest, generation=1, previous_release_id=None)

        records = self.repository.list_active_records()
        by_id = {record.entry.scenario_id: record for record in records}
        self.assertEqual(
            {record.entry.audience for record in records},
            {"development", "published"},
        )
        loaded = by_id[published.scenario.scenario_id]
        self.assertEqual(loaded.entry.audience, "published")
        self.assertEqual(loaded.release_id, manifest.release_id)
        self.assertEqual(loaded.release_no, manifest.release_no)
        self.assertEqual(loaded.release_checksum, manifest.checksum)
        verified = RuntimeBundleV1.model_validate(
            {
                "course": loaded.engine.course.model_dump(mode="json"),
                "scenario": loaded.engine.scenario.model_dump(mode="json"),
            }
        )
        self.assertEqual(verified.course.checksum, published.course.checksum)
        self.assertEqual(verified.scenario.checksum, published.scenario.checksum)

    def test_exact_history_survives_publish_and_rollback_with_full_identity(self):
        first = _runtime_bundle(build_dayu_bundle())
        first_manifest = _build_v2_manifest(first, release_no=1)
        _write_v2_release(self.root, first_manifest, first)
        _activate(
            self.root,
            first_manifest,
            generation=1,
            previous_release_id=None,
        )

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(engine.dispose)
        service = GameRuntimeService(self.repository, GameRuntimeStore(engine))
        _, session = service.start_session(
            first.scenario.scenario_id,
            user_id="release-history-student",
            release_pin=_release_pin(first_manifest, first),
            now=NOW,
        )
        legacy_lookup = self.repository.get_exact(
            first.scenario.scenario_id,
            first.scenario.scenario_version,
            str(first.scenario.checksum),
        )
        self.assertEqual(legacy_lookup.course.checksum, first.course.checksum)

        second = _bundle_with_course_version(first, content_version=2)
        second_manifest = _build_v2_manifest(
            second,
            release_no=2,
            parent=first_manifest,
        )
        _write_v2_release(self.root, second_manifest, second)
        _activate(
            self.root,
            second_manifest,
            generation=2,
            previous_release_id=first_manifest.release_id,
        )

        old_engine = _get_exact(self.repository, first)
        current_engine = _get_exact(self.repository, second)
        self.assertEqual(old_engine.course.checksum, first.course.checksum)
        self.assertEqual(current_engine.course.checksum, second.course.checksum)
        with self.assertRaisesRegex(ScenarioIntegrityError, "ambiguous"):
            self.repository.get_exact(
                first.scenario.scenario_id,
                first.scenario.scenario_version,
                str(first.scenario.checksum),
            )
        with self.assertRaises(ScenarioCatalogNotFound):
            self.repository.get_exact(
                first.scenario.scenario_id,
                first.scenario.scenario_version,
                str(first.scenario.checksum),
                course_id=first.course.course_id,
                lesson_id=first.course.lesson_id,
                course_content_version=second.course.content_version,
                course_checksum=str(first.course.checksum),
            )
        self.assertEqual(
            service.get_session(session.session_id).course_checksum,
            first.course.checksum,
        )

        rollback_manifest = _build_v2_manifest(
            first,
            release_no=3,
            parent=second_manifest,
            operation="rollback",
            restored_from_release_id=first_manifest.release_id,
        )
        _write_v2_release(self.root, rollback_manifest, first)
        _activate(
            self.root,
            rollback_manifest,
            generation=3,
            previous_release_id=second_manifest.release_id,
        )

        self.assertEqual(
            service.get_session(session.session_id).course_checksum,
            first.course.checksum,
        )
        self.assertEqual(
            _get_exact(self.repository, second).course.checksum,
            second.course.checksum,
        )

    def test_published_start_requires_exact_reachable_pin_and_full_idempotency(self):
        first = _runtime_bundle(build_dayu_bundle())
        first_manifest = _build_v2_manifest(first, release_no=1)
        _write_v2_release(self.root, first_manifest, first)
        _activate(
            self.root,
            first_manifest,
            generation=1,
            previous_release_id=None,
        )
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(engine.dispose)
        service = GameRuntimeService(self.repository, GameRuntimeStore(engine))
        pin = _release_pin(first_manifest, first)

        with self.assertRaises(PublishedScenarioPinRequired):
            service.start_session(
                first.scenario.scenario_id,
                user_id="pin-student",
                client_request_id="pin-start-001",
                now=NOW,
            )

        invalid_pins = (
            pin.model_copy(update={"release_id": f"{RELEASE_PREFIX}-0099"}),
            pin.model_copy(update={"release_no": pin.release_no + 1}),
            pin.model_copy(update={"release_checksum": "f" * 64}),
            pin.model_copy(update={"course_id": "C-wrong"}),
            pin.model_copy(update={"lesson_id": "lesson-wrong"}),
            pin.model_copy(
                update={"course_content_version": pin.course_content_version + 1}
            ),
            pin.model_copy(update={"course_checksum": "f" * 64}),
            pin.model_copy(update={"scenario_version": pin.scenario_version + 1}),
            pin.model_copy(update={"scenario_checksum": "f" * 64}),
        )
        for invalid_pin in invalid_pins:
            with self.subTest(invalid_pin=invalid_pin):
                with self.assertRaises(ScenarioCatalogNotFound):
                    service.start_session(
                        first.scenario.scenario_id,
                        user_id="pin-student",
                        client_request_id="pin-start-001",
                        release_pin=invalid_pin,
                        now=NOW,
                    )

        summary, started = service.start_session(
            first.scenario.scenario_id,
            user_id="pin-student",
            client_request_id="pin-start-001",
            release_pin=pin,
            now=NOW,
        )
        retry_summary, retry = service.start_session(
            first.scenario.scenario_id,
            user_id="pin-student",
            client_request_id="pin-start-001",
            release_pin=pin,
            now=NOW,
        )
        self.assertEqual(retry, started)
        self.assertEqual(retry_summary, summary)
        self.assertEqual(summary.release_id, first_manifest.release_id)
        self.assertEqual(summary.release_no, first_manifest.release_no)
        self.assertEqual(summary.release_checksum, first_manifest.checksum)

        second = _bundle_with_course_version(first, content_version=2)
        second_manifest = _build_v2_manifest(
            second,
            release_no=2,
            parent=first_manifest,
        )
        _write_v2_release(self.root, second_manifest, second)
        _activate(
            self.root,
            second_manifest,
            generation=2,
            previous_release_id=first_manifest.release_id,
        )

        old_summary, old_session = service.start_session(
            first.scenario.scenario_id,
            user_id="pin-student",
            client_request_id="pin-start-old-after-publish",
            release_pin=pin,
            now=NOW,
        )
        new_pin = _release_pin(second_manifest, second)
        new_summary, new_session = service.start_session(
            second.scenario.scenario_id,
            user_id="pin-student",
            client_request_id="pin-start-new-after-publish",
            release_pin=new_pin,
            now=NOW,
        )
        self.assertEqual(old_summary.release_id, first_manifest.release_id)
        self.assertEqual(old_session.course_checksum, first.course.checksum)
        self.assertEqual(new_summary.release_id, second_manifest.release_id)
        self.assertEqual(new_session.course_checksum, second.course.checksum)

        with self.assertRaises(DuplicateStartConflict):
            service.start_session(
                second.scenario.scenario_id,
                user_id="pin-student",
                client_request_id="pin-start-001",
                release_pin=new_pin,
                now=NOW,
            )

    def test_reused_artifacts_in_new_release_cannot_relabel_idempotent_session(self):
        bundle = _runtime_bundle(build_dayu_bundle())
        first_manifest = _build_v2_manifest(bundle, release_no=1)
        _write_v2_release(self.root, first_manifest, bundle)
        _activate(
            self.root,
            first_manifest,
            generation=1,
            previous_release_id=None,
        )
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(engine.dispose)
        store = GameRuntimeStore(engine)
        service = GameRuntimeService(self.repository, store)
        _, first_session = service.start_session(
            bundle.scenario.scenario_id,
            user_id="release-reuse-student",
            client_request_id="release-reuse-start-001",
            release_pin=_release_pin(first_manifest, bundle),
            now=NOW,
        )
        stored_identity = store.load_session(
            first_session.session_id
        ).envelope.release_identity
        self.assertIsNotNone(stored_identity)
        self.assertEqual(stored_identity.release_id, first_manifest.release_id)

        reused_manifest = _build_v2_manifest(
            bundle,
            release_no=2,
            parent=first_manifest,
        )
        _write_v2_release(self.root, reused_manifest, bundle)
        _activate(
            self.root,
            reused_manifest,
            generation=2,
            previous_release_id=first_manifest.release_id,
        )

        with self.assertRaises(DuplicateStartConflict):
            service.start_session(
                bundle.scenario.scenario_id,
                user_id="release-reuse-student",
                client_request_id="release-reuse-start-001",
                release_pin=_release_pin(reused_manifest, bundle),
                now=NOW,
            )
        summary, second_session = service.start_session(
            bundle.scenario.scenario_id,
            user_id="release-reuse-student",
            client_request_id="release-reuse-start-002",
            release_pin=_release_pin(reused_manifest, bundle),
            now=NOW,
        )
        self.assertNotEqual(second_session.session_id, first_session.session_id)
        self.assertEqual(summary.release_id, reused_manifest.release_id)

    def test_valid_but_unreachable_release_pin_fails_without_creating_session(self):
        bundle = _runtime_bundle(build_dayu_bundle())
        active_manifest = _build_v2_manifest(bundle, release_no=1)
        _write_v2_release(self.root, active_manifest, bundle)
        _activate(
            self.root,
            active_manifest,
            generation=1,
            previous_release_id=None,
        )
        isolated_manifest = _build_v2_manifest(bundle, release_no=9)
        _write_v2_release(self.root, isolated_manifest, bundle)
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.addCleanup(engine.dispose)
        service = GameRuntimeService(self.repository, GameRuntimeStore(engine))

        with self.assertRaises(ScenarioCatalogNotFound):
            service.start_session(
                bundle.scenario.scenario_id,
                user_id="isolated-release-student",
                client_request_id="isolated-release-start-001",
                release_pin=_release_pin(isolated_manifest, bundle),
                now=NOW,
            )
        summary, session = service.start_session(
            bundle.scenario.scenario_id,
            user_id="isolated-release-student",
            client_request_id="isolated-release-start-001",
            release_pin=_release_pin(active_manifest, bundle),
            now=NOW,
        )
        self.assertEqual(summary.release_id, active_manifest.release_id)
        self.assertEqual(session.course_checksum, bundle.course.checksum)

    def test_static_catalog_rejects_published_and_exact_matches_inactive_identity(self):
        bundle = _runtime_bundle(build_shangyang_bundle())
        entry = _write_static_bundle(
            self.root,
            bundle,
            name="static-history",
            active=False,
        )
        _write_catalog(self.root, [entry])

        self.assertEqual(self.repository.list_active_records(), ())
        self.assertEqual(
            _get_exact(self.repository, bundle).scenario.checksum,
            bundle.scenario.checksum,
        )
        with self.assertRaises(ScenarioCatalogNotFound):
            self.repository.get_exact(
                bundle.scenario.scenario_id,
                bundle.scenario.scenario_version,
                str(bundle.scenario.checksum),
                course_id=bundle.course.course_id,
                lesson_id=bundle.course.lesson_id,
                course_content_version=bundle.course.content_version,
                course_checksum="f" * 64,
            )

        entry["audience"] = "published"
        _write_catalog(self.root, [entry])
        with self.assertRaisesRegex(ScenarioFileError, "audience=development"):
            self.repository.load_catalog()

    def test_published_release_shadows_same_id_development_entry(self):
        development = _runtime_bundle(build_dayu_bundle())
        entry = _write_static_bundle(self.root, development, name="duplicate")
        _write_catalog(self.root, [entry])
        published = _bundle_with_course_version(development, content_version=2)
        manifest = _build_v2_manifest(published, release_no=1)
        _write_v2_release(self.root, manifest, published)
        _activate(self.root, manifest, generation=1, previous_release_id=None)

        records = self.repository.list_active_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].entry.scenario_id, published.scenario.scenario_id)
        self.assertEqual(records[0].entry.audience, "published")
        self.assertEqual(
            records[0].entry.course_content_version,
            published.course.content_version,
        )
        self.assertEqual(
            _get_exact(self.repository, development).course.checksum,
            development.course.checksum,
        )
        self.assertEqual(
            _get_exact(self.repository, published).course.checksum,
            published.course.checksum,
        )

    def test_exact_lookup_ignores_unrelated_corrupted_active_course(self):
        target = _runtime_bundle(build_dayu_bundle())
        target_manifest = _build_v2_manifest(target, release_no=1)
        _write_v2_release(self.root, target_manifest, target)
        _activate(
            self.root,
            target_manifest,
            generation=1,
            previous_release_id=None,
        )

        unrelated = _runtime_bundle(build_shangyang_bundle())
        unrelated_manifest = _build_v2_manifest(unrelated, release_no=1)
        _write_v2_release(self.root, unrelated_manifest, unrelated)
        _activate(
            self.root,
            unrelated_manifest,
            generation=1,
            previous_release_id=None,
        )
        scenario_path = self.root / unrelated_manifest.items[0].scenarios[0].path
        raw = _read_json(scenario_path)
        raw["title"] = "tampered"
        _write_json(scenario_path, raw)

        loaded = _get_exact(self.repository, target)
        self.assertEqual(loaded.course.checksum, target.course.checksum)
        with self.assertRaises(ScenarioIntegrityError):
            self.repository.list_active_records()

    def test_pointer_manifest_and_artifact_tampering_fail_closed(self):
        for target in ("pointer", "manifest", "artifact"):
            with self.subTest(target=target):
                root = self.root / target
                content.configure(root)
                _write_catalog(root, [])
                repository = _repository(root)
                bundle = _runtime_bundle(build_dayu_bundle())
                manifest = _build_v2_manifest(bundle, release_no=1)
                _write_v2_release(root, manifest, bundle)
                pointer_path = _activate(
                    root,
                    manifest,
                    generation=1,
                    previous_release_id=None,
                )

                if target == "pointer":
                    raw = _read_json(pointer_path)
                    raw["activated_by"] = "tampered"
                    _write_json(pointer_path, raw)
                elif target == "manifest":
                    manifest_path = _manifest_path(root, manifest)
                    raw = _read_json(manifest_path)
                    raw["note"] = "tampered"
                    _write_json(manifest_path, raw)
                else:
                    scenario_path = root / manifest.items[0].scenarios[0].path
                    raw = _read_json(scenario_path)
                    raw["title"] = "tampered"
                    _write_json(scenario_path, raw)

                with self.assertRaises(
                    (ScenarioFileError, ScenarioIntegrityError)
                ):
                    repository.list_active_records()
                content.configure(self.root)


def _repository(root: Path) -> ScenarioCatalogRepository:
    return ScenarioCatalogRepository(
        content_root=root,
        catalog_path="scenarios/catalog.v1.json",
    )


def _runtime_bundle(source: RuntimeBundleV1) -> RuntimeBundleV1:
    return RuntimeBundleV1(course=source.course, scenario=source.scenario)


def _release_pin(
    manifest: CourseReleaseManifestV2,
    bundle: RuntimeBundleV1,
) -> ScenarioReleasePinV1:
    return ScenarioReleasePinV1(
        release_id=manifest.release_id,
        release_no=manifest.release_no,
        release_checksum=manifest.checksum,
        course_id=bundle.course.course_id,
        lesson_id=bundle.course.lesson_id,
        course_content_version=bundle.course.content_version,
        course_checksum=bundle.course.checksum,
        scenario_version=bundle.scenario.scenario_version,
        scenario_checksum=bundle.scenario.checksum,
    )


def _bundle_with_course_version(
    source: RuntimeBundleV1,
    *,
    content_version: int,
) -> RuntimeBundleV1:
    raw = source.course.model_dump(mode="python")
    raw["content_version"] = content_version
    raw["title"] = f"{raw['title']} release {content_version}"
    raw["checksum"] = "0" * 64
    provisional = CoursePackageV1.model_validate(raw)
    raw["checksum"] = calculate_contract_checksum(provisional)
    course = CoursePackageV1.model_validate(raw)
    return RuntimeBundleV1(course=course, scenario=source.scenario)


def _build_v2_manifest(
    bundle: RuntimeBundleV1,
    *,
    release_no: int,
    parent: CourseReleaseManifestV2 | None = None,
    operation: str | None = None,
    restored_from_release_id: str | None = None,
) -> CourseReleaseManifestV2:
    course = bundle.course
    scenario = bundle.scenario
    course_descriptor = _descriptor(
        kind="course-package",
        schema_version=course.schema_version,
        artifact_id=course.package_id,
        course_id=course.course_id,
        lesson_id=course.lesson_id,
        version=course.content_version,
        checksum=str(course.checksum),
    )
    scenario_descriptor = _descriptor(
        kind="scenario-template",
        schema_version=scenario.schema_version,
        artifact_id=scenario.scenario_id,
        course_id=scenario.course_id,
        lesson_id=scenario.lesson_id,
        version=scenario.scenario_version,
        checksum=str(scenario.checksum),
    )
    manifest = CourseReleaseManifestV2(
        release_id=f"{RELEASE_PREFIX}-{release_no:04d}",
        release_no=release_no,
        course_id=course.course_id,
        operation=operation or ("bootstrap" if parent is None else "publish"),
        parent_release_id=parent.release_id if parent is not None else None,
        restored_from_release_id=restored_from_release_id,
        created_at=NOW,
        created_by="release-test",
        items=(
            CourseReleaseItemV2(
                lesson_id=course.lesson_id,
                course_id=course.course_id,
                content_version=course.content_version,
                source_path=(
                    f"sealed/{course.lesson_id}-v{course.content_version:03d}.json"
                ),
                source_checksum=str(
                    course.compatibility.source_checksum or course.checksum
                ),
                course_package=course_descriptor,
                scenarios=(scenario_descriptor,),
                primary_scenario_id=scenario.scenario_id,
            ),
        ),
        checksum="0" * 64,
    )
    return sign_release_metadata(manifest)


def _descriptor(
    *,
    kind: str,
    schema_version: str,
    artifact_id: str,
    course_id: str,
    lesson_id: str,
    version: int,
    checksum: str,
) -> RuntimeArtifactDescriptorV1:
    return RuntimeArtifactDescriptorV1(
        kind=kind,
        schema_version=schema_version,
        artifact_id=artifact_id,
        course_id=course_id,
        lesson_id=lesson_id,
        version=version,
        checksum=checksum,
        path=runtime_artifact_path(
            kind=kind,
            artifact_id=artifact_id,
            course_id=course_id,
            lesson_id=lesson_id,
            version=version,
            checksum=checksum,
        ),
    )


def _write_v2_release(
    root: Path,
    manifest: CourseReleaseManifestV2,
    bundle: RuntimeBundleV1,
) -> None:
    item = manifest.items[0]
    _write_json(
        root / item.course_package.path,
        bundle.course.model_dump(mode="json"),
    )
    _write_json(
        root / item.scenarios[0].path,
        bundle.scenario.model_dump(mode="json"),
    )
    _write_manifest(root, manifest)


def _write_manifest(
    root: Path,
    manifest: CourseReleaseManifestV1 | CourseReleaseManifestV2,
) -> None:
    _write_json(_manifest_path(root, manifest), manifest.model_dump(mode="json"))


def _manifest_path(
    root: Path,
    manifest: CourseReleaseManifestV1 | CourseReleaseManifestV2,
) -> Path:
    return (
        root
        / "releases"
        / "manifests"
        / manifest.course_id
        / f"{manifest.release_id}.json"
    )


def _activate(
    root: Path,
    manifest: CourseReleaseManifestV1 | CourseReleaseManifestV2,
    *,
    generation: int,
    previous_release_id: str | None,
) -> Path:
    pointer = sign_release_metadata(
        ActiveReleasePointerV1(
            course_id=manifest.course_id,
            release_id=manifest.release_id,
            release_no=manifest.release_no,
            manifest_path=(
                f"releases/manifests/{manifest.course_id}/"
                f"{manifest.release_id}.json"
            ),
            manifest_checksum=manifest.checksum,
            generation=generation,
            previous_release_id=previous_release_id,
            activated_at=NOW,
            activated_by="release-test",
            checksum="0" * 64,
        )
    )
    path = root / "releases" / "active" / f"{manifest.course_id}.json"
    _write_json(path, pointer.model_dump(mode="json"))
    return path


def _write_static_bundle(
    root: Path,
    bundle: RuntimeBundleV1,
    *,
    name: str,
    active: bool = True,
) -> dict[str, object]:
    course_path = f"development/{name}/course.json"
    scenario_path = f"development/{name}/scenario.json"
    _write_json(root / course_path, bundle.course.model_dump(mode="json"))
    _write_json(root / scenario_path, bundle.scenario.model_dump(mode="json"))
    return {
        "scenario_id": bundle.scenario.scenario_id,
        "scenario_version": bundle.scenario.scenario_version,
        "scenario_checksum": bundle.scenario.checksum,
        "course_id": bundle.course.course_id,
        "lesson_id": bundle.course.lesson_id,
        "course_content_version": bundle.course.content_version,
        "course_checksum": bundle.course.checksum,
        "course_path": course_path,
        "scenario_path": scenario_path,
        "active": active,
        "audience": "development",
    }


def _write_catalog(root: Path, entries: list[dict[str, object]]) -> None:
    _write_json(
        root / "scenarios" / "catalog.v1.json",
        {"schema_version": "scenario-catalog/v1", "entries": entries},
    )


def _get_exact(
    repository: ScenarioCatalogRepository,
    bundle: RuntimeBundleV1,
):
    return repository.get_exact(
        bundle.scenario.scenario_id,
        bundle.scenario.scenario_version,
        str(bundle.scenario.checksum),
        course_id=bundle.course.course_id,
        lesson_id=bundle.course.lesson_id,
        course_content_version=bundle.course.content_version,
        course_checksum=str(bundle.course.checksum),
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
