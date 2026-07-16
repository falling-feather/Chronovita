from __future__ import annotations

import json
import re
from pathlib import Path


REQUIRED_DOCUMENTS = (
    Path("docs/01-开发者文档.md"),
    Path("docs/02-项目规划与设计总纲.md"),
    Path("docs/03-内容设计工作手册.md"),
    Path("docs/05-发布历史与归档.md"),
    Path("docs/06-内容编辑建设清单.md"),
    Path("docs/adr/ADR-0015-生产身份与数据边界.md"),
    Path("docs/adr/ADR-0016-数据库版本迁移与备份恢复.md"),
)
REQUIRED_PLAN_IDS = ("OPS-001", "QA-001", "SEC-001")


def validate_project_docs(project_root: Path) -> list[str]:
    errors: list[str] = []
    documents: dict[Path, str] = {}
    for relative_path in REQUIRED_DOCUMENTS:
        path = project_root / relative_path
        if not path.is_file():
            errors.append(f"missing required document: {relative_path.as_posix()}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append(f"document is not valid UTF-8: {relative_path.as_posix()}")
            continue
        if "\x00" in text:
            errors.append(f"document contains a NUL byte: {relative_path.as_posix()}")
        documents[relative_path] = text

    version_path = project_root / "services/version.py"
    if not version_path.is_file():
        errors.append("missing application version module: services/version.py")
        return errors
    version_match = re.search(
        r'^APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"$',
        version_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if version_match is None:
        errors.append("services/version.py does not contain a valid APP_VERSION")
        return errors

    marker = f"V{version_match.group(1)}"
    for relative_path in REQUIRED_DOCUMENTS[:2] + (REQUIRED_DOCUMENTS[3],):
        text = documents.get(relative_path)
        if text is not None and marker not in "\n".join(text.splitlines()[:12]):
            errors.append(
                f"current version marker {marker} is missing near the top of "
                f"{relative_path.as_posix()}"
            )

    release_history = documents.get(Path("docs/05-发布历史与归档.md"), "")
    if release_history and f"当前版本：{marker}" not in release_history:
        errors.append("release history current-version line does not match APP_VERSION")

    project_plan = documents.get(Path("docs/02-项目规划与设计总纲.md"), "")
    for plan_id in REQUIRED_PLAN_IDS:
        if project_plan and plan_id not in project_plan:
            errors.append(f"project plan is missing required task id: {plan_id}")
    return errors


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    errors = validate_project_docs(project_root)
    print(
        json.dumps(
            {"ok": not errors, "errors": errors},
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
