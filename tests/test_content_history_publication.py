import shutil
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services import persistence
from services.content_history.publication import (
    PUBLICATION_NAMESPACE,
    PublicationConflict,
    PublicationNotFound,
    PublicationStore,
    PublicationStoreError,
    load_repository_binding,
    new_publication_record,
    publication_checkpoint,
)
from services.contracts.archive_examples import (
    build_dayu_publish_request,
    build_example_repository_binding,
)
from services.contracts.archive_v1 import CourseArchivePublishRequestV1


class ContentHistoryPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = (
            Path.cwd() / ".tmp-content-history-publication-tests" / uuid.uuid4().hex
        )
        self.tmp_root.mkdir(parents=True)
        persistence.init_engine(str(self.tmp_root / "publication.db"))
        self.store = PublicationStore()
        self.binding = build_example_repository_binding()
        self.request = build_dayu_publish_request()
        self.now = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)

    def tearDown(self):
        persistence.close_engine()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_create_is_idempotent_on_full_operation_key(self):
        first = new_publication_record(
            self.binding,
            self.request,
            requested_by="teacher-a",
            requested_at=self.now,
        )
        stored, created = self.store.create_or_get(first)
        self.assertTrue(created)
        self.assertEqual(stored, first)

        alternate_request = CourseArchivePublishRequestV1.model_validate(
            {
                **self.request.model_dump(mode="json"),
                "client_request_id": "another-browser-request",
                "change_summary": "后一次重复点击不能覆盖首个发布意图。",
            }
        )
        alternate = new_publication_record(
            self.binding,
            alternate_request,
            requested_by="teacher-b",
            requested_at=self.now + timedelta(seconds=1),
        )
        reused, created = self.store.create_or_get(alternate)

        self.assertFalse(created)
        self.assertEqual(reused, first)
        self.assertEqual(len(self.store.list()), 1)

    def test_checkpoints_are_signed_and_compare_and_set(self):
        requested = new_publication_record(
            self.binding,
            self.request,
            requested_by="teacher-a",
            requested_at=self.now,
        )
        self.store.create_or_get(requested)
        preparing = publication_checkpoint(
            requested,
            status="preparing",
            attempt=1,
            updated_at=self.now + timedelta(seconds=1),
        )
        self.store.checkpoint(requested, preparing)
        pushing = publication_checkpoint(
            preparing,
            status="pushing",
            base_sha="1" * 40,
            updated_at=self.now + timedelta(seconds=2),
        )
        self.store.checkpoint(preparing, pushing)

        self.assertEqual(
            self.store.get(requested.intent.publication_id),
            pushing,
        )
        with self.assertRaises(PublicationConflict):
            self.store.checkpoint(preparing, pushing)

    def test_tampered_record_is_rejected_on_read(self):
        requested = new_publication_record(
            self.binding,
            self.request,
            requested_by="teacher-a",
            requested_at=self.now,
        )
        self.store.create_or_get(requested)
        payload = requested.model_dump(mode="json")
        payload["updated_at"] = (self.now + timedelta(days=1)).isoformat()
        persistence.kv_set(
            PUBLICATION_NAMESPACE,
            requested.intent.operation_key,
            payload,
        )

        with self.assertRaises(PublicationStoreError):
            self.store.get(requested.intent.publication_id)

    def test_missing_publication_has_stable_error(self):
        with self.assertRaises(PublicationNotFound) as caught:
            self.store.get("pub-" + "0" * 32)
        self.assertEqual(caught.exception.code, "content_publication_not_found")

    def test_checked_in_target_resolves_to_private_fine_grained_binding(self):
        binding = load_repository_binding("infra/content-history-target.json")

        self.assertEqual(binding.repository_id, 1311692460)
        self.assertEqual(
            binding.full_name,
            "falling-feather/Chronovita-Course-Content",
        )
        self.assertEqual(binding.visibility, "private")
        self.assertEqual(binding.credential_kind, "fine_grained_token")
        self.assertEqual(
            binding.allowed_modes,
            ("pull_request", "direct_commit"),
        )


if __name__ == "__main__":
    unittest.main()
