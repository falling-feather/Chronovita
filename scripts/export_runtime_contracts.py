from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.contracts.archive_examples import (
    ARCHIVE_EXAMPLE_PACKAGE_DIRECTORY,
    archive_example_documents,
    archive_example_package_files,
)
from services.contracts.archive_v1 import (
    ARCHIVE_SCHEMA_DOCUMENTS,
    schema_document as archive_schema_document,
)
from services.contracts.examples import example_documents
from services.contracts.release_examples import (
    release_example_documents,
    release_v3_example_documents,
)
from services.contracts.release_v2 import (
    RELEASE_SCHEMA_DOCUMENTS,
    RELEASE_V3_SCHEMA_DOCUMENTS,
)
from services.contracts.evidence_v1 import (
    EVIDENCE_SCHEMA_DOCUMENTS,
    evidence_schema_document,
)
from services.contracts.v1 import SCHEMA_DOCUMENTS, schema_document


SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "v1"
EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "v1"
RELEASE_SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "releases" / "v2"
RELEASE_EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "releases" / "v2"
RELEASE_V3_SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "releases" / "v3"
RELEASE_V3_EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "releases" / "v3"
EVIDENCE_SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "evidence" / "v1"
ARCHIVE_SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "archive" / "v1"
ARCHIVE_EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "archive" / "v1"
ARCHIVE_EXAMPLE_PACKAGE_DIR = (
    ARCHIVE_EXAMPLE_DIR / ARCHIVE_EXAMPLE_PACKAGE_DIRECTORY
)


def export_runtime_contracts() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_V3_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_V3_EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    schema_documents = {
        filename: schema_document(model, schema_id)
        for filename, (model, schema_id) in SCHEMA_DOCUMENTS.items()
    }
    examples = example_documents()
    release_schema_documents = {
        filename: builder() for filename, builder in RELEASE_SCHEMA_DOCUMENTS.items()
    }
    release_v3_schema_documents = {
        filename: builder() for filename, builder in RELEASE_V3_SCHEMA_DOCUMENTS.items()
    }
    release_examples = release_example_documents()
    release_v3_examples = release_v3_example_documents()
    evidence_schema_documents = {
        filename: evidence_schema_document(model, schema_id)
        for filename, (model, schema_id) in EVIDENCE_SCHEMA_DOCUMENTS.items()
    }
    archive_schema_documents = {
        filename: archive_schema_document(model, schema_id, comment)
        for filename, (model, schema_id, comment) in ARCHIVE_SCHEMA_DOCUMENTS.items()
    }
    archive_examples = archive_example_documents()
    archive_package_files = archive_example_package_files()
    _remove_stale_json(SCHEMA_DIR, set(schema_documents))
    _remove_stale_json(EXAMPLE_DIR, set(examples))
    _remove_stale_json(RELEASE_SCHEMA_DIR, set(release_schema_documents))
    _remove_stale_json(RELEASE_EXAMPLE_DIR, set(release_examples))
    _remove_stale_json(RELEASE_V3_SCHEMA_DIR, set(release_v3_schema_documents))
    _remove_stale_json(RELEASE_V3_EXAMPLE_DIR, set(release_v3_examples))
    _remove_stale_json(EVIDENCE_SCHEMA_DIR, set(evidence_schema_documents))
    _remove_stale_json(ARCHIVE_SCHEMA_DIR, set(archive_schema_documents))
    _remove_stale_json(ARCHIVE_EXAMPLE_DIR, set(archive_examples))

    for filename, document in schema_documents.items():
        _write_json(SCHEMA_DIR / filename, document)
    for filename, document in examples.items():
        _write_json(EXAMPLE_DIR / filename, document.model_dump(mode="json"))
    for filename, document in release_schema_documents.items():
        _write_json(RELEASE_SCHEMA_DIR / filename, document)
    for filename, document in release_examples.items():
        _write_json(
            RELEASE_EXAMPLE_DIR / filename,
            document.model_dump(mode="json"),
        )
    for filename, document in release_v3_schema_documents.items():
        _write_json(RELEASE_V3_SCHEMA_DIR / filename, document)
    for filename, document in release_v3_examples.items():
        _write_json(
            RELEASE_V3_EXAMPLE_DIR / filename,
            document.model_dump(mode="json"),
        )
    for filename, document in evidence_schema_documents.items():
        _write_json(EVIDENCE_SCHEMA_DIR / filename, document)
    for filename, document in archive_schema_documents.items():
        _write_json(ARCHIVE_SCHEMA_DIR / filename, document)
    for filename, document in archive_examples.items():
        _write_json(
            ARCHIVE_EXAMPLE_DIR / filename,
            document.model_dump(mode="json"),
        )
    _sync_binary_tree(ARCHIVE_EXAMPLE_PACKAGE_DIR, archive_package_files)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _remove_stale_json(directory: Path, expected_filenames: set[str]) -> None:
    for path in directory.glob("*.json"):
        if path.name not in expected_filenames:
            path.unlink()


def _sync_binary_tree(directory: Path, payloads: dict[str, bytes]) -> None:
    expected = {
        PurePosixPath(relative_path).as_posix()
        for relative_path in payloads
    }
    if directory.exists():
        for path in directory.rglob("*"):
            if path.is_file() and path.relative_to(directory).as_posix() not in expected:
                path.unlink()

    for relative_path, payload in payloads.items():
        parts = PurePosixPath(relative_path).parts
        target = directory.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    if directory.exists():
        directories = sorted(
            (path for path in directory.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for path in directories:
            if not any(path.iterdir()):
                path.rmdir()


if __name__ == "__main__":
    export_runtime_contracts()
    print(f"Exported schemas to {SCHEMA_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported examples to {EXAMPLE_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported release schemas to {RELEASE_SCHEMA_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported release examples to {RELEASE_EXAMPLE_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported V3 release schemas to {RELEASE_V3_SCHEMA_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported V3 release examples to {RELEASE_V3_EXAMPLE_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported evidence schemas to {EVIDENCE_SCHEMA_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported archive schemas to {ARCHIVE_SCHEMA_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported archive examples to {ARCHIVE_EXAMPLE_DIR.relative_to(REPO_ROOT)}")
