import json
import shutil
import unittest
import uuid
from pathlib import Path
from zipfile import ZipFile

from services import content
from services.content import workflow as content_workflow
from services.content_history.archive import (
    ARCHIVE_RENDERER_VERSION,
    ArchiveBuildError,
    _format_layer,
    _preview_html,
    archive_download_filename,
    build_course_archive,
    build_course_archive_zip,
)
from services.contracts.archive_examples import (
    build_dayu_archive_release,
    build_dayu_sealed_lesson,
)
from services.contracts.archive_v1 import ARCHIVE_MANIFEST_FILENAME
from services.contracts.examples import build_dayu_bundle


class ContentHistoryArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = (
            Path.cwd() / ".tmp-content-history-archive-tests" / uuid.uuid4().hex
        )
        self.tmp_root.mkdir(parents=True)
        content.configure(self.tmp_root)
        self.release = build_dayu_archive_release()
        self.sealed = build_dayu_sealed_lesson()
        self.bundle = build_dayu_bundle()
        self._write_release_sources()

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass
        content.configure()

    def test_build_is_deterministic_and_zip_preserves_exact_files(self):
        first = build_course_archive(
            self.release.course_id,
            self.release.release_id,
        )
        second = build_course_archive(
            self.release.course_id,
            self.release.release_id,
        )

        self.assertEqual(first.manifest, second.manifest)
        self.assertEqual(dict(first.files), dict(second.files))
        self.assertEqual(
            first.manifest.renderer.renderer_version,
            ARCHIVE_RENDERER_VERSION,
        )
        self.assertIn(ARCHIVE_MANIFEST_FILENAME, first.files)
        self.assertTrue(
            archive_download_filename(first.manifest).endswith(
                f"-课程归档-{self.release.release_id}.zip"
            )
        )

        first_zip = build_course_archive_zip(first)
        self.assertEqual(first_zip, build_course_archive_zip(second))
        zip_path = self.tmp_root / "archive.zip"
        zip_path.write_bytes(first_zip)
        with ZipFile(zip_path) as bundle:
            self.assertEqual(
                bundle.namelist(),
                sorted(first.files, key=str.casefold),
            )
            for name, raw in first.files.items():
                self.assertEqual(bundle.read(name), raw)
                self.assertEqual(
                    bundle.getinfo(name).date_time,
                    (1980, 1, 1, 0, 0, 0),
                )

    def test_exact_source_bytes_participate_in_archive_identity(self):
        first = build_course_archive(
            self.release.course_id,
            self.release.release_id,
        )
        source_path = content.content_root() / self.release.items[0].source_path
        compact = json.dumps(
            self.sealed.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        source_path.write_bytes(compact)

        second = build_course_archive(
            self.release.course_id,
            self.release.release_id,
        )
        sealed_archive_path = next(
            item.path
            for item in second.manifest.files
            if item.kind == "sealed-lesson"
        )
        self.assertNotEqual(
            first.manifest.archive_checksum,
            second.manifest.archive_checksum,
        )
        self.assertEqual(second.files[sealed_archive_path], compact)

    def test_tampered_release_source_is_rejected(self):
        source_path = content.content_root() / self.release.items[0].source_path
        payload = self.sealed.model_dump(mode="json")
        payload["title"] = "被篡改的标题"
        source_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ArchiveBuildError,
            "sealed lesson does not match release item",
        ):
            build_course_archive(
                self.release.course_id,
                self.release.release_id,
            )

    def test_renderer_preserves_teacher_markup_as_format_and_html(self):
        marked = self.sealed.model_copy(
            update={
                "body": [
                    "## **水利治理**与==制度变迁==",
                    "【治水】依靠{{红色:协作}}与{{大字:长期规划}}。",
                ]
            }
        )
        layer = _format_layer(marked)
        preview = _preview_html(marked)

        self.assertEqual(layer["paragraphs"][0]["block"], "heading_2")
        self.assertIn(
            {"text": "水利治理", "marks": ["bold"]},
            layer["paragraphs"][0]["segments"],
        )
        self.assertIn("<h3><strong>水利治理</strong>", preview)
        self.assertIn("<mark>制度变迁</mark>", preview)
        self.assertIn('<span class="keyword">治水</span>', preview)
        self.assertIn('<span class="text-red">协作</span>', preview)
        self.assertIn('<span class="text-large">长期规划</span>', preview)

    def _write_release_sources(self) -> None:
        item = self.release.items[0]
        documents = {
            item.source_path: self.sealed.model_dump(mode="json"),
            item.course_package.path: self.bundle.course.model_dump(mode="json"),
            item.scenarios[0].path: self.bundle.scenario.model_dump(mode="json"),
            (
                f"releases/manifests/{self.release.course_id}/"
                f"{self.release.release_id}.json"
            ): self.release.model_dump(mode="json"),
        }
        for relative_path, payload in documents.items():
            path = content.content_root().joinpath(*relative_path.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        pointer = content_workflow._sign(
            content_workflow.ActiveReleasePointer(
                course_id=self.release.course_id,
                release_id=self.release.release_id,
                release_no=self.release.release_no,
                manifest_path=(
                    f"releases/manifests/{self.release.course_id}/"
                    f"{self.release.release_id}.json"
                ),
                manifest_checksum=self.release.checksum,
                generation=1,
                activated_at=self.release.created_at,
                activated_by=self.release.created_by,
                checksum="0" * 64,
            ),
            content_workflow.ActiveReleasePointer,
        )
        pointer_path = (
            content.release_dir() / "active" / f"{self.release.course_id}.json"
        )
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        pointer_path.write_text(
            json.dumps(
                pointer.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
