# Chronovita Content Packages

This directory is the file-based content handoff area for the current admin content workflow.

- `drafts/`: editable JSON drafts saved by `/api/v1/admin/content/drafts`.
- `sealed/`: versioned JSON files created by `/api/v1/admin/content/drafts/{lesson_id}/seal`.
- `/admin/content`: teacher-facing low-code editor for writing body text, keyword tags, focus blocks and source material without hand-editing JSON.

The browser keeps an unsaved local draft, `Save draft` persists a server-side file under `drafts/`, and `Seal` creates an immutable version under `sealed/` plus a downloadable JSON export.

Sealed files are the canonical exchange format for content review, Git submission and course-service import during this phase. Keep historical facts traceable through `source_refs`, and keep AI/RAG-facing material in `facts`, `people[].persona`, `qa_points`, `level_goals`, `saga_material` and `sandbox_material`.
