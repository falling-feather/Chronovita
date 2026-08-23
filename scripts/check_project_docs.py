from __future__ import annotations

import json
import re
from pathlib import Path


CORE_DOCUMENTS = (
    Path("doc/00-项目总纲.md"),
    Path("doc/01-开发者文档.md"),
    Path("doc/02-项目规划.md"),
    Path("doc/03-开发历史.md"),
)
COMPATIBILITY_DOCUMENTS = {
    Path("docs/00-项目总纲.md"): "../doc/00-项目总纲.md",
    Path("docs/01-开发者文档.md"): "../doc/01-开发者文档.md",
    Path("docs/02-项目规划与设计总纲.md"): "../doc/02-项目规划.md",
    Path("docs/05-发布历史与归档.md"): "../doc/03-开发历史.md",
}
SPECIALTY_DOCUMENTS = (
    Path("docs/03-内容设计工作手册.md"),
    Path("docs/04-资料整理与依据库.md"),
    Path("docs/06-内容编辑建设清单.md"),
    Path("docs/07-课程内容历史库运维指南.md"),
)
ARCHITECTURE_DOCUMENTS = (
    Path("docs/adr/ADR-0015-生产身份与数据边界.md"),
    Path("docs/adr/ADR-0016-数据库版本迁移与备份恢复.md"),
    Path("docs/adr/ADR-0017-课程内容历史库与Git发布边界.md"),
)
REQUIRED_DOCUMENTS = (
    CORE_DOCUMENTS
    + tuple(COMPATIBILITY_DOCUMENTS)
    + SPECIALTY_DOCUMENTS
    + ARCHITECTURE_DOCUMENTS
)
REQUIRED_DIRECTORIES = (
    Path("doc/01-子文档"),
    Path("doc/02-子文档"),
    Path("doc/03-子文档"),
    Path("doc/image"),
)
VERSIONED_DOCUMENTS = CORE_DOCUMENTS
STANDARD_METADATA_DOCUMENTS = CORE_DOCUMENTS + SPECIALTY_DOCUMENTS
STANDARD_METADATA_MARKERS = (
    "> **文档梗概**：",
    "> **具体规划法则**：",
    "> **最后一次更新时间**：",
    "> **更新者**：",
    "## 目录",
)
REQUIRED_PLAN_TASKS = tuple(range(1, 12))
REQUIRED_BRANCH_ROLES = ("`main`", "`houduan`", "`class`", "`qianduan`", "`backup/v*`")


def validate_project_docs(project_root: Path) -> list[str]:
    errors: list[str] = []
    documents: dict[Path, str] = {}
    for relative_path in REQUIRED_DIRECTORIES:
        if not (project_root / relative_path).is_dir():
            errors.append(f"missing required document directory: {relative_path.as_posix()}")
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
    for relative_path in VERSIONED_DOCUMENTS:
        text = documents.get(relative_path)
        if text is not None and marker not in "\n".join(text.splitlines()[:24]):
            errors.append(
                f"current version marker {marker} is missing near the top of "
                f"{relative_path.as_posix()}"
            )

    for relative_path in STANDARD_METADATA_DOCUMENTS:
        text = documents.get(relative_path)
        if text is None:
            continue
        for metadata_marker in STANDARD_METADATA_MARKERS:
            if metadata_marker not in "\n".join(text.splitlines()[:64]):
                errors.append(
                    f"standard metadata marker {metadata_marker!r} is missing near "
                    f"the top of {relative_path.as_posix()}"
                )

    for relative_path, canonical_target in COMPATIBILITY_DOCUMENTS.items():
        compatibility_text = documents.get(relative_path, "")
        compatibility_header = "\n".join(compatibility_text.splitlines()[:16])
        if compatibility_text and (
            "兼容状态" not in compatibility_header
            or canonical_target not in compatibility_header
        ):
            errors.append(
                f"compatibility document does not point to its canonical source: "
                f"{relative_path.as_posix()}"
            )

    release_history = documents.get(Path("doc/03-开发历史.md"), "")
    release_header = "\n".join(release_history.splitlines()[:24])
    if release_history and marker not in release_header:
        errors.append("development history does not match APP_VERSION")
    if release_history and "当前已提交版本" not in release_header:
        errors.append("development history does not declare the committed baseline")

    project_plan = documents.get(Path("doc/02-项目规划.md"), "")
    for task_number in REQUIRED_PLAN_TASKS:
        task_marker = f"**任务 {task_number}｜"
        if project_plan and task_marker not in project_plan:
            errors.append(
                f"project plan is missing current task marker: task {task_number}"
            )

    project_overview = documents.get(Path("doc/00-项目总纲.md"), "")
    for branch_name in REQUIRED_BRANCH_ROLES:
        if project_overview and branch_name not in project_overview:
            errors.append(
                f"project overview is missing branch responsibility: {branch_name}"
            )
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
