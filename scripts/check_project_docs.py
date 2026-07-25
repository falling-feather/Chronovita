from __future__ import annotations

import json
import re
from pathlib import Path


REQUIRED_DOCUMENTS = (
    Path("docs/00-项目总纲.md"),
    Path("docs/01-开发者文档.md"),
    Path("docs/02-项目规划与设计总纲.md"),
    Path("docs/03-内容设计工作手册.md"),
    Path("docs/04-资料整理与依据库.md"),
    Path("docs/05-发布历史与归档.md"),
    Path("docs/06-内容编辑建设清单.md"),
    Path("docs/07-课程内容历史库运维指南.md"),
    Path("docs/adr/ADR-0015-生产身份与数据边界.md"),
    Path("docs/adr/ADR-0016-数据库版本迁移与备份恢复.md"),
    Path("docs/adr/ADR-0017-课程内容历史库与Git发布边界.md"),
)
VERSIONED_DOCUMENTS = (
    Path("docs/00-项目总纲.md"),
    Path("docs/01-开发者文档.md"),
    Path("docs/02-项目规划与设计总纲.md"),
    Path("docs/05-发布历史与归档.md"),
)
STANDARD_METADATA_DOCUMENTS = tuple(
    Path(f"docs/{number:02d}-{name}.md")
    for number, name in (
        (0, "项目总纲"),
        (1, "开发者文档"),
        (2, "项目规划与设计总纲"),
        (3, "内容设计工作手册"),
        (4, "资料整理与依据库"),
        (5, "发布历史与归档"),
        (6, "内容编辑建设清单"),
        (7, "课程内容历史库运维指南"),
    )
)
STANDARD_METADATA_MARKERS = (
    "> **文档梗概**：",
    "> **具体规划法则**：",
    "> **最后一次更新时间**：",
    "> **更新者**：",
    "## 目录",
)
REQUIRED_PLAN_IDS = (
    "OPS-001",
    "QA-001",
    "SEC-001",
    "DOC-002",
    "ARCH-004",
    "OPS-002",
    "BE-006",
    "FE-004",
    "OPS-003",
    "QA-002",
)
REQUIRED_BRANCH_ROLES = ("`main`", "`houduan`", "`class`", "`qianduan`", "`backup/v*`")


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
            if metadata_marker not in "\n".join(text.splitlines()[:40]):
                errors.append(
                    f"standard metadata marker {metadata_marker!r} is missing near "
                    f"the top of {relative_path.as_posix()}"
                )

    release_history = documents.get(Path("docs/05-发布历史与归档.md"), "")
    release_header = "\n".join(release_history.splitlines()[:24])
    if release_history and not re.search(
        rf"> \*\*当前基线\*\*：{re.escape(marker)}(?:\b|（)",
        release_header,
    ):
        errors.append(
            "release history current baseline does not match APP_VERSION"
        )
    if release_history and "“开发历史”唯一原件" not in release_header:
        errors.append(
            "release history does not declare its compatibility authority"
        )

    project_plan = documents.get(Path("docs/02-项目规划与设计总纲.md"), "")
    for plan_id in REQUIRED_PLAN_IDS:
        if project_plan and plan_id not in project_plan:
            errors.append(f"project plan is missing required task id: {plan_id}")

    project_overview = documents.get(Path("docs/00-项目总纲.md"), "")
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
