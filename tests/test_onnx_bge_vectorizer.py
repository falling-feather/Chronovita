from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

from services.rag.retrieval import OnnxBgeVectorizer, RagIndexUnavailable


class FakeTokenizer:
    instances: list["FakeTokenizer"] = []

    @classmethod
    def from_file(cls, path):
        instance = cls()
        instance.path = path
        instance.calls = []
        cls.instances.append(instance)
        return instance

    def enable_truncation(self, **kwargs):
        self.truncation = kwargs

    def enable_padding(self, **kwargs):
        self.padding = kwargs

    def add_special_tokens(self, tokens):
        self.special_tokens = tokens

    def encode_batch(self, texts):
        self.calls.append(texts)
        return [types.SimpleNamespace(ids=[101, 7, 102], attention_mask=[1, 1, 1])
                for _ in texts]


class FakeSession:
    instances: list["FakeSession"] = []
    invalid_output = None

    def __init__(self, path, *, sess_options, providers):
        self.path, self.options, self.providers = path, sess_options, providers
        self.calls = []
        self.instances.append(self)

    def get_inputs(self):
        return [types.SimpleNamespace(name=name)
                for name in ("input_ids", "attention_mask", "token_type_ids")]

    def run(self, names, inputs):
        self.calls.append((names, inputs))
        if self.invalid_output is not None:
            return [self.invalid_output]
        count, length = inputs["input_ids"].shape
        output = np.full((count, length, 512), 1000.0, dtype=np.float32)
        output[:, 0] = 0
        output[:, 0, :2] = [3, 4]
        return [output]


class OnnxBgeVectorizerTests(unittest.TestCase):
    def setUp(self):
        FakeSession.instances.clear()
        FakeSession.invalid_output = None
        FakeTokenizer.instances.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        files = {
            "config.json": json.dumps({"pad_token_id": 0}).encode(),
            "tokenizer_config.json": json.dumps({"model_max_length": 512, "pad_token": "[PAD]"}).encode(),
            "special_tokens_map.json": json.dumps({"cls_token": "[CLS]", "pad_token": "[PAD]"}).encode(),
            "tokenizer.json": b"checked-tokenizer-fixture",
            "model_optimized.onnx": b"checked-onnx-fixture",
        }
        for name, data in files.items():
            (self.root / name).write_bytes(data)
        manifest = {
            "schema_version": "rag-model-resource/v1", "model_id": "BAAI/bge-small-zh-v1.5",
            "source_repository": "Qdrant/bge-small-zh-v1.5",
            "source_revision": "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59", "dimension": 512,
            "license": "MIT", "license_url": "https://huggingface.co/BAAI/bge-small-zh-v1.5",
            "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                      for name, data in sorted(files.items())],
        }
        (self.root / "model-resource.json").write_text(json.dumps(manifest), encoding="utf-8")
        fake_ort = types.SimpleNamespace(
            InferenceSession=FakeSession, SessionOptions=types.SimpleNamespace,
            ExecutionMode=types.SimpleNamespace(ORT_SEQUENTIAL="sequential"),
        )
        self.modules = patch.dict(sys.modules, {
            "onnxruntime": fake_ort, "tokenizers": types.SimpleNamespace(Tokenizer=FakeTokenizer),
            "fastembed": None,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_offline_cpu_cls_embedding_preserves_query_without_added_instruction(self):
        vectorizer = OnnxBgeVectorizer(self.root)
        self.assertTrue(vectorizer.available)
        vector = vectorizer.embed_query("治水协作有什么代价？")
        self.assertEqual(len(vector), 512)
        self.assertAlmostEqual(vector[0], 0.6)
        self.assertAlmostEqual(vector[1], 0.8)
        self.assertEqual(vector[2:], (0.0,) * 510)
        tokenizer = FakeTokenizer.instances[0]
        self.assertEqual(tokenizer.calls, [["治水协作有什么代价？"]])
        self.assertEqual(tokenizer.truncation, {"max_length": 512})
        session = FakeSession.instances[0]
        self.assertEqual(session.providers, ["CPUExecutionProvider"])
        self.assertEqual(session.options.intra_op_num_threads, 2)
        self.assertEqual(session.options.inter_op_num_threads, 1)
        inputs = session.calls[0][1]
        self.assertTrue(all(value.dtype == np.int64 for value in inputs.values()))
        np.testing.assert_array_equal(inputs["token_type_ids"], np.zeros((1, 3), dtype=np.int64))

    def test_passages_are_batched_and_share_one_checked_runtime(self):
        vectorizer = OnnxBgeVectorizer(self.root)
        vectors = vectorizer.embed_passages([f"片段 {index}" for index in range(17)])
        self.assertEqual(len(vectors), 17)
        self.assertEqual(len(FakeSession.instances), 1)
        self.assertEqual([len(call) for call in FakeTokenizer.instances[0].calls], [16, 1])
        self.assertEqual(vectorizer.embed_passages([]), [])

    def test_disabled_missing_or_tampered_bundle_does_not_load_a_runtime(self):
        self.assertFalse(OnnxBgeVectorizer(self.root, enabled=False).available)
        self.assertFalse(OnnxBgeVectorizer(self.root / "missing").available)
        (self.root / "model_optimized.onnx").write_bytes(b"tampered")
        self.assertFalse(OnnxBgeVectorizer(self.root).available)
        self.assertEqual(FakeSession.instances, [])

    def test_runtime_load_failure_is_unavailable_not_a_fake_vector(self):
        with patch.object(FakeSession, "__init__", side_effect=RuntimeError("CPU runtime missing")):
            vectorizer = OnnxBgeVectorizer(self.root)
            self.assertFalse(vectorizer.available)
            with self.assertRaises(RagIndexUnavailable):
                vectorizer.embed_query("治水")

    def test_invalid_shape_zero_and_nonfinite_output_are_rejected(self):
        for output in (np.ones((1, 12)), np.zeros((1, 512)), np.full((1, 512), np.nan)):
            with self.subTest(shape=output.shape):
                FakeSession.invalid_output = output
                with self.assertRaises(RagIndexUnavailable):
                    OnnxBgeVectorizer(self.root).embed_query("治水")
