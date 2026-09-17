"""只读 SQLite 数据库查看器。

这个脚本不经过应用服务，也不会写入数据库。它适合本地课堂开发时快速查看
表结构、行数和少量数据预览。默认读取当前工作树的 ``data/chronovita.db``，
也可以用 ``--database`` 指定另一个 SQLite 文件。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = REPO_ROOT / "data" / "chronovita.db"
DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_CELL_CHARS = 240


def running_database_path() -> Path | None:
    """Read the last local review runtime target, when one is available."""

    runtime_file = REPO_ROOT / ".chronovita-review" / "runtime.json"
    try:
        runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
        raw_path = runtime.get("database_path")
        if isinstance(raw_path, str) and raw_path.strip():
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = REPO_ROOT / candidate
            if candidate.is_file():
                return candidate
    except (OSError, ValueError, TypeError):
        # The viewer still works when the review service has never been started
        # or its runtime marker is incomplete.
        return None
    return None


def resolve_database_path(raw_path: str | None) -> Path:
    """Resolve a database path without changing the process environment."""

    value = raw_path or os.environ.get("CHRONO_SQLITE_PATH", "")
    if not value:
        return running_database_path() or DEFAULT_DATABASE
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def quote_identifier(value: str) -> str:
    """Quote a SQLite identifier; table names come from sqlite_master."""

    return '"' + value.replace('"', '""') + '"'


def open_readonly_database(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"找不到数据库文件：{path}")
    # mode=ro prevents this viewer from creating or changing a database file.
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    return connection


def list_tables(connection: sqlite3.Connection) -> list[tuple[str, int]]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    result: list[tuple[str, int]] = []
    for row in rows:
        table_name = str(row["name"])
        try:
            count = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM {quote_identifier(table_name)}"
                ).fetchone()["count"]
            )
        except sqlite3.DatabaseError:
            count = -1
        result.append((table_name, count))
    return result


def table_rows(
    connection: sqlite3.Connection,
    table_name: str,
    max_rows: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    columns = [
        str(row["name"])
        for row in connection.execute(
            f"PRAGMA table_info({quote_identifier(table_name)})"
        ).fetchall()
    ]
    rows = connection.execute(
        f"SELECT * FROM {quote_identifier(table_name)} LIMIT ?", (max_rows,)
    ).fetchall()
    return columns, [dict(row) for row in rows]


def display_value(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return f"<BLOB {len(value)} bytes>"
    text = str(value).replace("\r", " ").replace("\n", " ")
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


class DatabaseViewer:
    def __init__(self, database_path: Path, *, max_rows: int, max_cell_chars: int) -> None:
        self.database_path = database_path
        self.max_rows = max_rows
        self.max_cell_chars = max_cell_chars
        self.connection: sqlite3.Connection | None = None
        self.tables: list[tuple[str, int]] = []
        self.current_columns: list[str] = []
        self.current_rows: list[dict[str, Any]] = []

        self.root = tk.Tk()
        self.root.title("Chronovita · 数据库查看器（只读）")
        self.root.geometry("1280x780")
        self.root.minsize(900, 560)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_style()
        self._build_layout()

        try:
            self.connection = open_readonly_database(self.database_path)
            self.reload_tables()
        except (OSError, sqlite3.DatabaseError) as exc:
            self._show_error(str(exc))

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("Muted.TLabel", foreground="#687385")
        style.configure("Status.TLabel", foreground="#536273")

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Chronovita 数据库查看器", style="Title.TLabel").pack(anchor="w")
        self.path_var = tk.StringVar(value=f"只读 · {self.database_path}")
        ttk.Label(header, textvariable=self.path_var, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Button(header, text="刷新", command=self.reload_tables).pack(anchor="e", pady=(0, 2))

        body = ttk.PanedWindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(left, weight=1)
        body.add(right, weight=4)

        ttk.Label(left, text="数据表").pack(anchor="w")
        filter_frame = ttk.Frame(left)
        filter_frame.pack(fill="x", pady=(6, 8))
        ttk.Label(filter_frame, text="过滤").pack(side="left")
        self.filter_var = tk.StringVar()
        filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var)
        filter_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.filter_var.trace_add("write", lambda *_: self._render_table_list())

        table_frame = ttk.Frame(left)
        table_frame.pack(fill="both", expand=True)
        self.table_tree = ttk.Treeview(
            table_frame,
            columns=("table", "rows"),
            show="headings",
            selectmode="browse",
        )
        self.table_tree.heading("table", text="表名")
        self.table_tree.heading("rows", text="行数")
        self.table_tree.column("table", width=210, anchor="w")
        self.table_tree.column("rows", width=72, anchor="e")
        table_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table_tree.yview)
        self.table_tree.configure(yscrollcommand=table_scroll.set)
        self.table_tree.pack(side="left", fill="both", expand=True)
        table_scroll.pack(side="right", fill="y")
        self.table_tree.bind("<<TreeviewSelect>>", self._on_table_selected)

        self.table_title_var = tk.StringVar(value="请选择左侧数据表")
        ttk.Label(right, textvariable=self.table_title_var, style="Title.TLabel").pack(anchor="w")
        self.table_meta_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.table_meta_var, style="Muted.TLabel").pack(anchor="w", pady=(3, 8))

        grid_frame = ttk.Frame(right)
        grid_frame.pack(fill="both", expand=True)
        self.data_tree = ttk.Treeview(grid_frame, show="headings", selectmode="browse")
        data_y = ttk.Scrollbar(grid_frame, orient="vertical", command=self.data_tree.yview)
        data_x = ttk.Scrollbar(grid_frame, orient="horizontal", command=self.data_tree.xview)
        self.data_tree.configure(yscrollcommand=data_y.set, xscrollcommand=data_x.set)
        self.data_tree.grid(row=0, column=0, sticky="nsew")
        data_y.grid(row=0, column=1, sticky="ns")
        data_x.grid(row=1, column=0, sticky="ew")
        grid_frame.rowconfigure(0, weight=3)
        grid_frame.columnconfigure(0, weight=1)
        self.data_tree.bind("<<TreeviewSelect>>", self._on_row_selected)

        ttk.Label(right, text="选中行详情").pack(anchor="w", pady=(10, 4))
        detail_frame = ttk.Frame(right)
        detail_frame.pack(fill="both", expand=False)
        self.detail_text = tk.Text(detail_frame, height=8, wrap="none", state="disabled")
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        self.detail_text.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        self.status_var = tk.StringVar(value="等待加载")
        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w", pady=(8, 0))

    def _show_error(self, message: str) -> None:
        self.status_var.set(f"无法打开数据库：{message}")
        self.table_title_var.set("数据库不可用")
        self.table_meta_var.set("请检查路径，或使用 --database 指定 SQLite 文件")
        try:
            messagebox.showerror("数据库查看器", message, parent=self.root)
        except tk.TclError:
            pass

    def reload_tables(self) -> None:
        if self.connection is None:
            return
        try:
            selected = self.table_tree.selection()
            previous = self.table_tree.item(selected[0], "values")[0] if selected else ""
            self.tables = list_tables(self.connection)
            self._render_table_list()
            for item in self.table_tree.get_children():
                if self.table_tree.item(item, "values")[0] == previous:
                    self.table_tree.selection_set(item)
                    self.table_tree.focus(item)
                    self._on_table_selected()
                    break
            self.status_var.set(f"已加载 {len(self.tables)} 张表 · 仅显示每表前 {self.max_rows} 行")
        except sqlite3.DatabaseError as exc:
            self._show_error(str(exc))

    def _render_table_list(self) -> None:
        query = self.filter_var.get().strip().casefold()
        for item in self.table_tree.get_children():
            self.table_tree.delete(item)
        for table_name, count in self.tables:
            if query and query not in table_name.casefold():
                continue
            count_text = "?" if count < 0 else str(count)
            self.table_tree.insert("", "end", values=(table_name, count_text))

    def _on_table_selected(self, _event: tk.Event[Any] | None = None) -> None:
        selection = self.table_tree.selection()
        if not selection or self.connection is None:
            return
        table_name = str(self.table_tree.item(selection[0], "values")[0])
        try:
            columns, rows = table_rows(self.connection, table_name, self.max_rows)
        except sqlite3.DatabaseError as exc:
            self._show_error(str(exc))
            return
        self.current_columns = columns
        self.current_rows = rows
        self.table_title_var.set(table_name)
        self.table_meta_var.set(f"字段 {len(columns)} 个 · 预览 {len(rows)} 行")
        self._render_data_grid()
        self._set_detail("")

    def _render_data_grid(self) -> None:
        self.data_tree.delete(*self.data_tree.get_children())
        self.data_tree["columns"] = self.current_columns
        for column in self.current_columns:
            self.data_tree.heading(column, text=column)
            self.data_tree.column(column, width=max(110, min(260, len(column) * 13 + 50)), anchor="w")
        for row in self.current_rows:
            self.data_tree.insert(
                "",
                "end",
                values=tuple(display_value(row.get(column), self.max_cell_chars) for column in self.current_columns),
            )

    def _on_row_selected(self, _event: tk.Event[Any] | None = None) -> None:
        selection = self.data_tree.selection()
        if not selection:
            return
        index = self.data_tree.index(selection[0])
        if index >= len(self.current_rows):
            return
        self._set_detail(json.dumps(self.current_rows[index], ensure_ascii=False, indent=2, default=str))

    def _set_detail(self, value: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", value)
        self.detail_text.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="打开 Chronovita SQLite 数据库的只读 GUI 查看器")
    parser.add_argument("--database", help="SQLite 数据库路径；默认为 data/chronovita.db")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS, help="每张表最多预览的行数")
    parser.add_argument(
        "--max-cell-chars",
        type=int,
        default=DEFAULT_MAX_CELL_CHARS,
        help="表格单元格最多显示的字符数，详情面板仍显示整行内容",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_rows < 1 or args.max_cell_chars < 20:
        print("--max-rows 必须大于 0，--max-cell-chars 必须至少为 20", file=sys.stderr)
        return 2
    viewer = DatabaseViewer(
        resolve_database_path(args.database),
        max_rows=args.max_rows,
        max_cell_chars=args.max_cell_chars,
    )
    viewer.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
