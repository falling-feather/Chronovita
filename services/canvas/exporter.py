from __future__ import annotations

import json

from .models import CanvasBoard, ExportFormat


_KIND_LABEL = {
    "event": "事件",
    "figure": "人物",
    "policy": "政策",
    "place": "地理",
    "concept": "概念",
}


def _to_markdown(board: CanvasBoard) -> str:
    lines = [f"# {board.title}", ""]
    if board.summary:
        lines += [board.summary, ""]
    lines.append("## 节点")
    by_kind: dict[str, list] = {}
    for n in board.nodes:
        by_kind.setdefault(n.kind.value, []).append(n)
    for kind, items in by_kind.items():
        lines.append(f"### {_KIND_LABEL.get(kind, kind)}")
        for n in items:
            tail = f" — {n.detail}" if n.detail else ""
            period = f"（{n.period}）" if n.period else ""
            lines.append(f"- **{n.label}**{period}{tail}")
        lines.append("")
    lines.append("## 关系")
    id_to_label = {n.node_id: n.label for n in board.nodes}
    for e in board.edges:
        s = id_to_label.get(e.source_id, e.source_id)
        t = id_to_label.get(e.target_id, e.target_id)
        rel = f" — {e.label}" if e.label else ""
        lines.append(f"- {s} → {t}{rel}")
    return "\n".join(lines) + "\n"


def _to_mermaid(board: CanvasBoard) -> str:
    lines = ["graph LR"]
    for n in board.nodes:
        safe = n.label.replace('"', "'")
        lines.append(f'  {n.node_id}["{safe}"]')
    for e in board.edges:
        if e.label:
            lines.append(f'  {e.source_id} -->|{e.label}| {e.target_id}')
        else:
            lines.append(f'  {e.source_id} --> {e.target_id}')
    return "\n".join(lines) + "\n"


def export_board(board: CanvasBoard, fmt: ExportFormat) -> tuple[str, str]:
    if fmt is ExportFormat.JSON:
        return (
            json.dumps(board.model_dump(mode="json"), ensure_ascii=False, indent=2),
            "application/json; charset=utf-8",
        )
    if fmt is ExportFormat.MARKDOWN:
        return _to_markdown(board), "text/markdown; charset=utf-8"
    if fmt is ExportFormat.MERMAID:
        return _to_mermaid(board), "text/plain; charset=utf-8"
    raise ValueError(f"unsupported format: {fmt}")
