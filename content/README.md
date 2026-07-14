# Chronovita Content Packages

This directory is the file-based content handoff area for the current admin content workflow.

- `drafts/`: editable JSON drafts saved by `/api/v1/admin/content/drafts`.
- `sealed/`: versioned JSON files created by `/api/v1/admin/content/drafts/{lesson_id}/seal`.
- `workflows/`: signed per-lesson review state, validation report and audit events.
- `packages/v1/`: immutable legacy-compatibility `CoursePackageV1` mirrors; active V2 readers use the manifest's content-addressed runtime package instead.
- `schemas/releases/v2/`: generated JSON Schema for the joint course/runtime release manifest.
- `examples/releases/v2/`: development-only V2 release fixture; it is never scanned as published content.
- `runtime/v1/course-packages/`: immutable content-addressed course packages bound to exact scenario refs.
- `runtime/v1/scenarios/`: sealed scenario staging area and immutable artifacts referenced by V2 releases; file presence alone never publishes a scenario.
- `releases/manifests/{course_id}/`: immutable full-course release snapshots.
- `releases/active/{course_id}.json`: atomically replaced pointer to the student-visible release.
- `releases/transactions/{course_id}.json`: short-lived crash-recovery journal removed after a completed release.
- `releases/.locks/workflow-global.lock`: cross-process workflow/release lock; it never contains course content.
- `assets/people/`: teacher-maintained person profile packages.
- `assets/keywords/`: teacher-maintained keyword profile packages.
- `/admin/content`: teacher-facing low-code editor for writing body text, keyword tags, focus blocks and source material without hand-editing JSON.
- `/admin/content/preview`: direct preview route used by the editor's Preview button.

The browser keeps an unsaved local draft, and `Save draft` persists a server-side file under `drafts/`. Review state is independent from artifact state: sealing creates an immutable version, while only publishing changes student-visible content. Audit actors come from the authenticated server principal (`CHRONO_ADMIN_ACTOR`), not a client-supplied display name.

Teacher workflow:

1. On Windows, double-click `点我一键启动（部署）.cmd` in the project root.
   - First launch prepares `.venv`, installs `apps/api/requirements.txt`, installs `apps/web` npm dependencies, starts the API and web editor, then opens `/admin/content`. Later launches reuse API dependencies while the requirements hash is unchanged.
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
5. Click `Save draft`, then use `Validate` to run the minimum publication checks.
6. Submit the validated draft for review. The reviewer may return it with a required note or approve it.
7. Seal an approved draft. The student course API still serves the previously published release.
8. Optionally register a sealed `ScenarioTemplateV1` with `POST /api/v1/admin/content/runtime-scenarios`, then select its exact ID, version and checksum during publish.
9. Publish the sealed version to create a full-course V2 release manifest and move the active pointer. Omit `scenarios` or send `null` to preserve current bindings, send `[]` to remove them, or send an explicit list with exactly one `primary` item to replace them.
10. Use release history to roll back. Rollback creates a new immutable release, revalidates the historical course/scenario bundle, and switches both together.
11. Click `Export bundle` at any time to download:
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
- `services/contracts/release_v2.py`: strict V1/V2 manifest reader, content-addressed descriptors and release metadata checksum helpers.
- `services/content/runtime_artifacts.py`: sealed scenario registration, immutable runtime materialization and `RuntimeBundleV1` validation.
- `services/game_runtime/catalog.py`: development-only static catalog plus active V2 published scenarios and reachable-history exact lookup.

Regenerate and validate from the repository root:

```powershell
& ".\.venv\Scripts\python.exe" scripts\export_runtime_contracts.py
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v
```

The Dayu fixtures are development data. Historical body text, facts, persona material, and explanations marked `教师待审` must be replaced or approved by the teaching team before a real release. A V2 example manifest is only a contract fixture; publication remains controlled exclusively by an active release pointer.

Sealed files are immutable source artifacts for review and Git submission. The active release manifest, not the highest sealed filename, is authoritative for the course service. Public reads never scan `sealed/` for a presumed latest version. A pre-workflow sealed package must be explicitly whitelisted through `POST /api/v1/admin/content/releases/{course_id}/bootstrap-legacy` with exact `lesson_id` and `content_version` selections.

Publication and rollback prepare immutable manifests and all affected lesson workflow projections before atomically replacing the active pointer as the final student-visible commit. A signed transaction journal restores the previous projections when a process stops before activation, or finishes the target projections when activation already succeeded; API startup performs this recovery under a cross-process global workflow lock shared by save, review, seal, publish and rollback operations. Release activation revalidates every referenced sealed source, course package, scenario and `RuntimeBundleV1`, rejects a `lesson_id` or published `scenario_id` already active in another course, and uses optimistic preflight identity so concurrent publishers do not both move the same old pointer. Unreachable manifests left before a transaction journal was written are excluded from release history. Every read verifies signed metadata, checksums, canonical paths, IDs and versions; corruption fails closed. The static `content/scenarios/catalog.v1.json` accepts only `audience=development`; formal `audience=published` scenarios come exclusively from the active V2 release. Historical sessions resolve the full pinned course/scenario identity through reachable release history, so a later publish or rollback cannot silently substitute a newer artifact. Keep historical facts traceable through `source_refs`, and keep AI/RAG-facing material in `facts`, `people[].persona`, `qa_points`, `level_goals`, `saga_material` and `sandbox_material`.
