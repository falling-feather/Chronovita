import shutil
import unittest
import uuid
from pathlib import Path
from zipfile import ZipFile

from services import content, persistence
from services.content import scenario_authoring
from services.content_history.asset_archive import (
    ContentAssetArchiveBuildError,
    build_content_asset_archive,
    build_content_asset_archive_zip,
    content_asset_archive_download_filename,
)
from services.content_history.asset_service import ContentAssetPublicationService
from services.content_history.publication import (
    PublicationStore,
    new_publication_record,
)
from services.content_history.service import PublicationArchiveChanged
from services.contracts.archive_examples import (
    build_dayu_publish_request,
    build_example_repository_binding,
)
from services.contracts.archive_v1 import (
    ASSET_ARCHIVE_MANIFEST_FILENAME,
    ContentAssetArchivePublishRequestV1,
)
from tests.test_content_history_service import _FakeGitHub


class ContentAssetArchiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_root = (
            Path.cwd() / ".tmp-content-asset-history-tests" / uuid.uuid4().hex
        )
        self.tmp_root.mkdir(parents=True)
        content.configure(self.tmp_root / "content")
        persistence.init_engine(str(self.tmp_root / "publication.db"))
        self.binding = build_example_repository_binding()
        self._seed_assets()

    def tearDown(self):
        persistence.close_engine()
        content.configure()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_all_asset_kinds_build_deterministic_exact_archives(self):
        cases = (
            ("person", "li-hongzhang", 1),
            ("keyword", "yangwu-yundong", 1),
            ("scenario", "scenario-asset-sample", 1),
        )
        for kind, asset_id, version in cases:
            with self.subTest(kind=kind):
                first = build_content_asset_archive(kind, asset_id, version)
                second = build_content_asset_archive(kind, asset_id, version)
                self.assertEqual(first.manifest, second.manifest)
                self.assertEqual(dict(first.files), dict(second.files))
                self.assertIn(ASSET_ARCHIVE_MANIFEST_FILENAME, first.files)
                self.assertEqual(
                    first.manifest.archive_path.split("/", 1)[0],
                    {
                        "person": "people",
                        "keyword": "keywords",
                        "scenario": "scenarios",
                    }[kind],
                )
                self.assertTrue(
                    content_asset_archive_download_filename(
                        first.manifest
                    ).endswith("-归档.zip")
                )
                first_zip = build_content_asset_archive_zip(first)
                self.assertEqual(
                    first_zip,
                    build_content_asset_archive_zip(second),
                )
                zip_path = self.tmp_root / f"{kind}.zip"
                zip_path.write_bytes(first_zip)
                with ZipFile(zip_path) as bundle:
                    self.assertEqual(
                        bundle.namelist(),
                        sorted(first.files, key=str.casefold),
                    )
                    for name, raw in first.files.items():
                        self.assertEqual(bundle.read(name), raw)

    async def test_asset_publication_uses_asset_root_and_is_idempotent(self):
        archive = build_content_asset_archive("person", "li-hongzhang", 1)
        request = self._request(archive)
        github = _FakeGitHub(self.binding)
        service = ContentAssetPublicationService(
            binding=self.binding,
            github=github,
        )

        first = await service.submit(request, requested_by="teacher-a")
        second = await service.submit(request, requested_by="teacher-b")

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.publication.status, "succeeded")
        self.assertEqual(second.publication, first.publication)
        tree_call = next(call for call in github.calls if call[0] == "create_tree")
        self.assertTrue(
            all(
                path.startswith(
                    "assets/people/li-hongzhang/versions/v001/"
                )
                for path in tree_call[2]
            )
        )
        self.assertEqual(
            PublicationStore().list(
                asset_kind="person",
                asset_id="li-hongzhang",
                asset_version=1,
            ),
            (first.publication,),
        )
        self.assertEqual(PublicationStore().list(course_id="C-none"), ())

        course_record = new_publication_record(
            self.binding,
            build_dayu_publish_request(),
            requested_by="teacher-course",
        )
        PublicationStore().create_or_get(course_record)
        self.assertEqual(
            PublicationStore().list(publication_kind="asset"),
            (first.publication,),
        )
        self.assertEqual(
            PublicationStore().list(publication_kind="course"),
            (course_record,),
        )
        self.assertEqual(service.list(), (first.publication,))

    def test_archive_rejects_duplicate_keys_in_exact_source_bytes(self):
        path = (
            content.sealed_people_asset_dir()
            / "li-hongzhang-v001.json"
        )
        raw = path.read_text(encoding="utf-8")
        raw = raw.replace(
            '"name": "李鸿章",',
            '"name": "李鸿章",\n  "name": "李鸿章",',
            1,
        )
        path.write_text(raw, encoding="utf-8", newline="\n")

        with self.assertRaises(ContentAssetArchiveBuildError):
            build_content_asset_archive("person", "li-hongzhang", 1)

    async def test_preview_identity_drift_is_rejected_before_network(self):
        archive = build_content_asset_archive("keyword", "yangwu-yundong", 1)
        request = self._request(archive)
        changed_checksum = "f" * 64
        changed = ContentAssetArchivePublishRequestV1.model_validate(
            {
                **request.model_dump(mode="json"),
                "archive_id": f"arc-{changed_checksum[:32]}",
                "expected_archive_checksum": changed_checksum,
            }
        )
        github = _FakeGitHub(self.binding)
        service = ContentAssetPublicationService(
            binding=self.binding,
            github=github,
        )

        with self.assertRaises(PublicationArchiveChanged):
            await service.submit(changed, requested_by="teacher-a")

        self.assertEqual(github.calls, [])
        self.assertEqual(PublicationStore().list(), ())

    def _seed_assets(self) -> None:
        person = content.person_template()
        person.asset_id = "li-hongzhang"
        person.name = "李鸿章"
        content.save_person_profile(person)
        content.seal_person_profile(person.asset_id, sealed_by="publisher")

        keyword = content.keyword_template()
        keyword.asset_id = "yangwu-yundong"
        keyword.word = "洋务运动"
        content.save_keyword_profile(keyword)
        content.seal_keyword_profile(keyword.asset_id, sealed_by="publisher")

        scenario = scenario_authoring.scenario_draft_template()
        scenario.scenario_id = "scenario-asset-sample"
        scenario.course_id = "C-asset-sample"
        scenario.lesson_id = "asset-sample-lesson"
        scenario.title = "样板历史关卡"
        scenario_authoring.save_scenario_draft(
            scenario,
            saved_by="author",
        )
        scenario_authoring.seal_scenario_draft(
            scenario.scenario_id,
            sealed_by="publisher",
        )

    def _request(self, archive):
        return ContentAssetArchivePublishRequestV1(
            binding_id=self.binding.binding_id,
            asset_kind=archive.manifest.asset_kind,
            asset_id=archive.manifest.asset_id,
            version=archive.manifest.version,
            expected_source_checksum=archive.manifest.source_checksum,
            archive_id=archive.manifest.archive_id,
            expected_archive_checksum=archive.manifest.archive_checksum,
            client_request_id=f"test-{archive.manifest.asset_id}",
            change_summary="测试内容资产发布。",
        )


if __name__ == "__main__":
    unittest.main()
