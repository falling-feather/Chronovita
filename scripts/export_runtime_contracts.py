from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.contracts.examples import example_documents
from services.contracts.v1 import SCHEMA_DOCUMENTS, schema_document


SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "v1"
EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "v1"


def export_runtime_contracts() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    schema_documents = {
        filename: schema_document(model, schema_id)
        for filename, (model, schema_id) in SCHEMA_DOCUMENTS.items()
    }
    examples = example_documents()
    _remove_stale_json(SCHEMA_DIR, set(schema_documents))
    _remove_stale_json(EXAMPLE_DIR, set(examples))

    for filename, document in schema_documents.items():
        _write_json(SCHEMA_DIR / filename, document)
    for filename, document in examples.items():
        _write_json(EXAMPLE_DIR / filename, document.model_dump(mode="json"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _remove_stale_json(directory: Path, expected_filenames: set[str]) -> None:
    for path in directory.glob("*.json"):
        if path.name not in expected_filenames:
            path.unlink()


if __name__ == "__main__":
    export_runtime_contracts()
    print(f"Exported schemas to {SCHEMA_DIR.relative_to(REPO_ROOT)}")
    print(f"Exported examples to {EXAMPLE_DIR.relative_to(REPO_ROOT)}")
