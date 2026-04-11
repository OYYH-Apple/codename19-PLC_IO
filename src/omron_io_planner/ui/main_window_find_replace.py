# -*- coding: utf-8 -*-
"""主窗口：查找 / 替换对话框与表格匹配逻辑（Mixin）。"""
from __future__ import annotations

from .dialogs import FindReplaceDialog
from .io_table_widget import IoTableWidget


class MainWindowFindReplaceMixin:
    _find_replace_dialog: FindReplaceDialog | None
    _find_replace_context: dict[str, object]

    def _reset_find_replace_context(self) -> None:
        self._find_replace_context = {
            "table": None,
            "query": "",
            "case_sensitive": False,
            "direction": "forward",
            "current_column_only": False,
            "selected_only": False,
            "base_column": None,
            "match": None,
        }

    def _ensure_find_replace_dialog(self) -> FindReplaceDialog:
        if self._find_replace_dialog is None:
            dialog = FindReplaceDialog(self)
            dialog.find_next_requested.connect(self._find_next_in_current_table)
            dialog.replace_requested.connect(self._replace_current_in_current_table)
            dialog.replace_all_requested.connect(self._replace_all_in_current_table)
            dialog.search_options_changed.connect(self._reset_find_replace_context)
            self._find_replace_dialog = dialog
        return self._find_replace_dialog

    def _show_find_replace_dialog(self, *, replace_mode: bool) -> None:
        dialog = self._ensure_find_replace_dialog()
        dialog.set_replace_mode(replace_mode)
        dialog.set_status_text("")
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.focus_search_input()
        self._reset_find_replace_context()

    def _open_find_dialog(self) -> None:
        self._show_find_replace_dialog(replace_mode=False)

    def _open_replace_dialog(self) -> None:
        self._show_find_replace_dialog(replace_mode=True)

    def _current_channel_table_for_find_replace(self) -> IoTableWidget | None:
        table = self._current_channel_table()
        if table is None:
            message = "请先切换到具体分区编辑页，再使用查找替换。"
            self.statusBar().showMessage(message, 3000)
            dialog = self._find_replace_dialog
            if dialog is not None:
                dialog.set_status_text(message)
            return None
        table.flush_active_editor()
        return table

    def _current_find_replace_options(self, dialog: FindReplaceDialog, table: IoTableWidget) -> dict[str, object]:
        return {
            "case_sensitive": dialog.case_sensitive(),
            "direction": dialog.search_direction(),
            "current_column_only": dialog.current_column_only(),
            "selected_only": dialog.selected_only(),
            "base_column": table.currentColumn() if table.currentColumn() >= 0 else None,
        }

    def _find_replace_context_matches(self, table: IoTableWidget, query: str, options: dict[str, object]) -> bool:
        return (
            self._find_replace_context.get("table") is table
            and self._find_replace_context.get("query") == query
            and bool(self._find_replace_context.get("case_sensitive")) == bool(options.get("case_sensitive"))
            and str(self._find_replace_context.get("direction")) == str(options.get("direction"))
            and bool(self._find_replace_context.get("current_column_only")) == bool(options.get("current_column_only"))
            and bool(self._find_replace_context.get("selected_only")) == bool(options.get("selected_only"))
            and self._find_replace_context.get("base_column") == options.get("base_column")
        )

    def _current_find_match_for_request(self, table: IoTableWidget, query: str, options: dict[str, object]):
        if not self._find_replace_context_matches(table, query, options):
            return None
        match = self._find_replace_context.get("match")
        if table.match_still_valid(
            match,
            query,
            case_sensitive=bool(options.get("case_sensitive")),
            current_column_only=bool(options.get("current_column_only")),
            selected_only=bool(options.get("selected_only")),
            base_column=options.get("base_column"),
        ):
            return match
        return None

    def _set_find_replace_context(
        self,
        table: IoTableWidget,
        query: str,
        options: dict[str, object],
        match,
    ) -> None:
        self._find_replace_context = {
            "table": table,
            "query": query,
            "case_sensitive": bool(options.get("case_sensitive")),
            "direction": str(options.get("direction") or "forward"),
            "current_column_only": bool(options.get("current_column_only")),
            "selected_only": bool(options.get("selected_only")),
            "base_column": options.get("base_column"),
            "match": match,
        }

    def _find_replace_column_label(self, table: IoTableWidget, column: int) -> str:
        item = table.horizontalHeaderItem(column)
        return item.text() if item is not None else f"列 {column + 1}"

    def _find_next_in_current_table(self) -> None:
        dialog = self._ensure_find_replace_dialog()
        table = self._current_channel_table_for_find_replace()
        if table is None:
            return
        query = dialog.search_text().strip()
        if not query:
            dialog.set_status_text("请输入要查找的内容。")
            self.statusBar().showMessage("请输入要查找的内容", 2500)
            self._reset_find_replace_context()
            return
        options = self._current_find_replace_options(dialog, table)
        after = self._current_find_match_for_request(table, query, options)
        match = table.find_next_match(query, after=after, **options)
        if match is None:
            dialog.set_status_text(f"未找到“{query}”。")
            self.statusBar().showMessage(f"未找到“{query}”", 2500)
            self._reset_find_replace_context()
            return
        table.activate_search_match(match, preserve_selection=bool(options.get("selected_only")))
        self._set_find_replace_context(table, query, options, match)
        message = f"已定位：第 {match.row + 1} 行 · {self._find_replace_column_label(table, match.col)}"
        dialog.set_status_text(message)
        self.statusBar().showMessage(message, 2500)

    def _replace_current_in_current_table(self) -> None:
        dialog = self._ensure_find_replace_dialog()
        table = self._current_channel_table_for_find_replace()
        if table is None:
            return
        query = dialog.search_text().strip()
        if not query:
            dialog.set_status_text("请输入要查找的内容。")
            self.statusBar().showMessage("请输入要查找的内容", 2500)
            self._reset_find_replace_context()
            return
        options = self._current_find_replace_options(dialog, table)
        match = self._current_find_match_for_request(table, query, options)
        if match is None:
            match = table.find_next_match(query, **options)
            if match is None:
                dialog.set_status_text(f"未找到“{query}”。")
                self.statusBar().showMessage(f"未找到“{query}”", 2500)
                self._reset_find_replace_context()
                return
        table.activate_search_match(match, preserve_selection=bool(options.get("selected_only")))
        if not table.replace_match(match, dialog.replace_text()):
            dialog.set_status_text("当前匹配已失效，请重新查找。")
            self.statusBar().showMessage("当前匹配已失效，请重新查找", 2500)
            self._reset_find_replace_context()
            return
        next_anchor_start = (
            match.start
            if str(options.get("direction")) == "backward"
            else match.start + max(len(dialog.replace_text()), 1) - 1
        )
        anchor = match.__class__(
            match.row,
            match.col,
            next_anchor_start,
            max(1, len(dialog.replace_text())),
        )
        next_match = table.find_next_match(query, after=anchor, **options)
        if next_match is not None:
            table.activate_search_match(next_match, preserve_selection=bool(options.get("selected_only")))
            self._set_find_replace_context(table, query, options, next_match)
            message = f"已替换 1 处 · 下一处在第 {next_match.row + 1} 行"
        else:
            self._reset_find_replace_context()
            message = "已替换 1 处"
        dialog.set_status_text(message)
        self.statusBar().showMessage(message, 2500)

    def _replace_all_in_current_table(self) -> None:
        dialog = self._ensure_find_replace_dialog()
        table = self._current_channel_table_for_find_replace()
        if table is None:
            return
        query = dialog.search_text().strip()
        if not query:
            dialog.set_status_text("请输入要查找的内容。")
            self.statusBar().showMessage("请输入要查找的内容", 2500)
            return
        options = self._current_find_replace_options(dialog, table)
        count = table.replace_all_matches(
            query,
            dialog.replace_text(),
            case_sensitive=bool(options.get("case_sensitive")),
            current_column_only=bool(options.get("current_column_only")),
            selected_only=bool(options.get("selected_only")),
            base_column=options.get("base_column"),
        )
        if count <= 0:
            dialog.set_status_text(f"未找到“{query}”。")
            self.statusBar().showMessage(f"未找到“{query}”", 2500)
            self._reset_find_replace_context()
            return
        self._reset_find_replace_context()
        message = f"已替换 {count} 处"
        dialog.set_status_text(message)
        self.statusBar().showMessage(message, 3000)
