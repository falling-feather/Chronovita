from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import prepare_rag_model
from services.rag.retrieval import FastEmbedVectorizer


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_MANIFEST = (
    REPO_ROOT
    / "distribution"
    / "models"
    / "BAAI-bge-small-zh-v1.5"
    / "model-resource.json"
)


class _FakeTextEmbedding:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.calls.append(kwargs)

    def embed(self, texts, **_kwargs):
        return ([1.0] + [0.0] * 511 for _ in texts)

    def query_embed(self, texts):
        return ([1.0] + [0.0] * 511 for _ in texts)


class RagModelResourceTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeTextEmbedding.calls.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.model_root = Path(self.temp_dir.name)
        payload = b"offline-vector-model-fixture"
        (self.model_root / "tiny-model.bin").write_bytes(payload)
        self.manifest = {
            "schema_version": "rag-model-resource/v1",
            "model_id": "BAAI/bge-small-zh-v1.5",
            "source_repository": "Qdrant/bge-small-zh-v1.5",
            "source_revision": "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59",
            "dimension": 512,
            "license": "MIT",
            "license_url": "https://huggingface.co/BAAI/bge-small-zh-v1.5",
            "files": [
                {
                    "path": "tiny-model.bin",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            ],
        }
        self.manifest_path = self.model_root / "model-resource.json"
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_checked_bundle_loads_fastembed_in_offline_mode(self) -> None:
        fake_module = types.SimpleNamespace(TextEmbedding=_FakeTextEmbedding)
        with patch.dict(sys.modules, {"fastembed": fake_module}):
            vectorizer = FastEmbedVectorizer(self.model_root)
            self.assertTrue(vectorizer.available)
            vector = vectorizer.embed_query("课堂离线检索")

        self.assertEqual(len(vector), 512)
        self.assertEqual(
            _FakeTextEmbedding.calls,
            [
                {
                    "model_name": "BAAI/bge-small-zh-v1.5",
                    "specific_model_path": str(self.model_root),
                    "local_files_only": True,
                }
            ],
        )

    def test_tampered_model_file_disables_vector_path(self) -> None:
        (self.model_root / "tiny-model.bin").write_bytes(b"tampered")
        fake_module = types.SimpleNamespace(TextEmbedding=_FakeTextEmbedding)
        with patch.dict(sys.modules, {"fastembed": fake_module}):
            self.assertFalse(FastEmbedVectorizer(self.model_root).available)
        self.assertEqual(_FakeTextEmbedding.calls, [])

    def test_distribution_manifest_is_pinned_and_well_formed(self) -> None:
        manifest = prepare_rag_model._read_manifest(MODEL_MANIFEST)
        self.assertEqual(manifest["dimension"], 512)
        self.assertEqual(
            manifest["source_revision"],
            "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59",
        )
        self.assertEqual(len(manifest["files"]), 5)

    def test_manifest_rejects_escaping_file_path(self) -> None:
        self.manifest["files"][0]["path"] = "../outside.bin"
        self.manifest_path.write_text(
            json.dumps(self.manifest),
            encoding="utf-8",
        )
        with self.assertRaises(prepare_rag_model.ModelResourceError):
            prepare_rag_model._read_manifest(self.manifest_path)

    @unittest.skipUnless(
        hasattr(os, "symlink"),
        "This platform cannot create symbolic links.",
    )
    def test_symlinked_model_file_is_not_accepted(self) -> None:
        source = self.model_root / "tiny-model.bin"
        real_source = self.model_root / "real-model.bin"
        real_source.write_bytes(source.read_bytes())
        source.unlink()
        try:
            source.symlink_to(real_source)
        except OSError as exc:
            self.skipTest(f"symbolic links are unavailable: {exc}")
        fake_module = types.SimpleNamespace(TextEmbedding=_FakeTextEmbedding)
        with patch.dict(sys.modules, {"fastembed": fake_module}):
            self.assertFalse(FastEmbedVectorizer(self.model_root).available)


if __name__ == "__main__":
    unittest.main()
