# Chronovita Content Packages

This directory is the file-based content handoff area for the current admin content workflow.

- `drafts/`: editable JSON drafts saved by `/api/v1/admin/content/drafts`.
- `sealed/`: versioned JSON files created by `/api/v1/admin/content/drafts/{lesson_id}/seal`.
- `assets/people/`: teacher-maintained person profile packages.
- `assets/keywords/`: teacher-maintained keyword profile packages.
- `/admin/content`: teacher-facing low-code editor for writing body text, keyword tags, focus blocks and source material without hand-editing JSON.
- `/admin/content/preview`: direct preview route used by the editor's Preview button.

The browser keeps an unsaved local draft, `Save draft` persists a server-side file under `drafts/`, and `Seal` creates an immutable version under `sealed/` plus a downloadable export bundle.

Teacher workflow:

1. On Windows, double-click `点我一键启动（部署）.cmd` in the project root.
   - First launch prepares `.venv`, installs `apps/api/requirements.txt`, installs `apps/web` npm dependencies, starts the API and web editor, then opens `/admin/content`.
   - The `.cmd` launcher intentionally prints ASCII-only text to avoid Windows command prompt encoding issues.
   - Developer fallback: open `scripts/teacher-editor.cmd`, or run `scripts/teacher-editor.ps1`.
2. Choose a planned course from the editor's course-planning selector.
   - Or choose an existing implemented lesson from `已有课程初稿` and revise it directly.
3. Write lesson body text in the low-code body editor. Prefer the toolbar or the custom right-click menu for quick formatting:
   - `【keyword】` marks a keyword and auto-adds it to the keyword list.
   - `**bold text**` renders as bold.
   - `==red text==` renders as highlighted red text.
   - `{{红色:text}}`, `{{蓝色:text}}`, and `{{金色:text}}` render as colored emphasis.
   - `{{大字:text}}` and `{{小字:text}}` render as font-size emphasis.
   - Lines beginning with `#`, `##`, or `###` render as lesson body headings.
   - Lines beginning with `重点:`, `问题:`, or `目标:` can be parsed into facts, QA points, and level goals.
4. Click `Preview` to open the lesson preview page immediately.
5. Click `Save draft` to persist the editable server-side draft.
6. Click `Seal` or `Export bundle` to download:
   - `课程标题.json`: the canonical content layer.
   - `课程标题-格式层.json`: parsed rich-text segment metadata for 1:1 rendering checks.
   - `课程标题-预览.html`: standalone visual preview.
   - `课程标题-教师稿.md`: teacher-friendly handoff document.

The editor can also switch to `人物档案` or `关键词档案`. Those packages are saved under `assets/people/` and `assets/keywords/`, and exported with title-preserving names such as `李鸿章-人物档案.json` and `洋务运动-关键词档案.json`.

Seed examples currently included:

- `drafts/yangwu-yundong-tansuo.json`
- `assets/people/li-hongzhang.json`
- `assets/keywords/yangwu-yundong.json`

Runtime contract artifacts:

- `schemas/v1/`: JSON Schema 2020-12 documents for the four V1 artifacts plus the aggregate `RuntimeBundleV1` validator.
- `examples/v1/`: a complete Dayu flood-control technical fixture plus one file for each top-level contract.
- `services/contracts/`: the authoritative Pydantic models, cross-reference validation, checksum helpers, and the legacy lesson-package adapter.
- `scripts/export_runtime_contracts.py`: deterministic exporter for the committed schema and example files.

Regenerate and validate from the repository root:

```powershell
& ".\.venv\Scripts\python.exe" scripts\export_runtime_contracts.py
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v
```

The Dayu fixture is development data. Historical body text, facts, persona material, and explanations marked `教师待审` must be replaced or approved by the teaching team before a real release.

Sealed files are the canonical exchange format for content review, Git submission and course-service import during this phase. Keep historical facts traceable through `source_refs`, and keep AI/RAG-facing material in `facts`, `people[].persona`, `qa_points`, `level_goals`, `saga_material` and `sandbox_material`.
