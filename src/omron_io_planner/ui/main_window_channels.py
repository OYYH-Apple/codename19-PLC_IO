# -*- coding: utf-8 -*-
"""主窗口：通道选项卡、表格编辑与沉浸筛选（Mixin）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import IoChannel, IoPoint
from ..omron_zones import get_zone
from .data_type_delegate import DataTypeDelegate
from .dialogs import BatchGenerateDialog, BulkRowUpdateDialog
from .io_table_widget import IoTableWidget, _render_generation_template
from .main_window_constants import (
    COL_ADDR,
    COL_COMMENT,
    COL_DTYPE,
    COL_NAME,
    COL_RACK,
    COL_USAGE,
    PREVIEW_LABEL,
)
from .main_window_recents_menus import _get_prefs
from .main_window_utils import (
    _is_preview_tab_label,
    _make_action_btn,
    _make_immersive_btn,
    _next_address_value,
)
from .name_completer_delegate import NameCompleterDelegate
from .zone_info_panel import ZoneInfoPanel


class MainWindowChannelsMixin:

    # ── 通道编辑器（含分区信息侧边栏） ────────────────────────────────────

    def _make_channel_editor(self, zone_id: str = "") -> tuple[QWidget, IoTableWidget]:
        outer = QWidget()
        outer_h = QHBoxLayout(outer)
        outer_h.setContentsMargins(8, 8, 8, 8)
        outer_h.setSpacing(12)

        table = IoTableWidget()
        table.set_zone_id(zone_id)
        table.setItemDelegateForColumn(COL_DTYPE, DataTypeDelegate(table))
        table.setItemDelegateForColumn(COL_NAME, NameCompleterDelegate(table, table))
        table.setItemDelegateForColumn(COL_COMMENT, NameCompleterDelegate(table, table, source_column=COL_COMMENT))
        self._configure_table_from_preferences(table)
        table.contentDirty.connect(lambda reason, current=table: self._on_channel_table_dirty(current, reason))
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, table)
        find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find_shortcut.activated.connect(self._open_find_dialog)
        replace_shortcut = QShortcut(QKeySequence.StandardKey.Replace, table)
        replace_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        replace_shortcut.activated.connect(self._open_replace_dialog)
        table._find_shortcut = find_shortcut  # type: ignore[attr-defined]
        table._replace_shortcut = replace_shortcut  # type: ignore[attr-defined]

        table_shell = QWidget()
        table_shell_layout = QVBoxLayout(table_shell)
        table_shell_layout.setContentsMargins(0, 0, 0, 0)
        table_shell_layout.setSpacing(8)

        tools_bar = QWidget()
        tools_bar.setObjectName("editorToolsBar")
        tools_bar_layout = QVBoxLayout(tools_bar)
        tools_bar_layout.setContentsMargins(12, 10, 12, 10)
        tools_bar_layout.setSpacing(8)

        tools_header = QWidget(tools_bar)
        tools_header.setObjectName("editorToolsHeader")
        tools_header_layout = QHBoxLayout(tools_header)
        tools_header_layout.setContentsMargins(0, 0, 0, 0)
        tools_header_layout.setSpacing(10)

        tools_badge = QLabel("批量编辑", tools_header)
        tools_badge.setObjectName("editorToolsBadge")
        tools_summary = QLabel("围绕高频录入的 5 个动作：连续生成、整行统一设置、文本批量修饰。", tools_header)
        tools_summary.setObjectName("editorToolsSummary")
        tools_summary.setWordWrap(True)
        tools_header_layout.addWidget(tools_badge, 0)
        tools_header_layout.addWidget(tools_summary, 1)
        tools_bar_layout.addWidget(tools_header, 0)

        tools_buttons_row = QWidget(tools_bar)
        tools_buttons_row.setObjectName("editorToolsButtonsRow")
        tools_layout = QHBoxLayout(tools_buttons_row)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)
        btn_generate = _make_action_btn("批量生成", "从当前行开始，按模板连续生成多行", compact=True)
        btn_bulk_rows = _make_action_btn("批量设置", "先选中整行，再统一设置数据类型、机架位置、使用", compact=True)
        btn_prefix = _make_action_btn("加前缀", "对选中单元格追加统一前缀", compact=True)
        btn_suffix = _make_action_btn("加后缀", "对选中单元格追加统一后缀", compact=True)
        btn_number = _make_action_btn("加编号", "对选中单元格按顺序追加编号", compact=True)
        btn_guide = _make_action_btn("使用说明", "查看批量编辑的常用操作说明", compact=True)
        btn_guide.setObjectName("batchEditGuideButton")
        for button in (btn_generate, btn_bulk_rows, btn_prefix, btn_suffix, btn_number, btn_guide):
            tools_layout.addWidget(button, 0)
        tools_layout.addStretch(1)
        btn_generate.clicked.connect(lambda: self._open_batch_generate(table))
        btn_bulk_rows.clicked.connect(lambda: self._open_bulk_row_update(table))
        btn_prefix.clicked.connect(lambda: self._open_bulk_text_transform(table, "prefix"))
        btn_suffix.clicked.connect(lambda: self._open_bulk_text_transform(table, "suffix"))
        btn_number.clicked.connect(lambda: self._open_bulk_text_transform(table, "number"))
        btn_guide.clicked.connect(self._show_batch_edit_guide)
        tools_bar_layout.addWidget(tools_buttons_row, 0)

        batch_hint = QLabel(
            "点左侧行号可选整行；文本操作只处理已选中的单元格；所有批量操作都支持 Ctrl+Z 撤回。"
        )
        batch_hint.setObjectName("batchEditHint")
        batch_hint.setWordWrap(True)
        tools_bar_layout.addWidget(batch_hint, 0)

        focus_bar = QWidget()
        focus_bar.setObjectName("immersiveFocusBar")
        focus_bar.setHidden(not self._immersive_mode)
        focus_layout = QVBoxLayout(focus_bar)
        focus_layout.setContentsMargins(10, 8, 10, 8)
        focus_layout.setSpacing(6)

        filter_row = QWidget(focus_bar)
        filter_row.setObjectName("immersiveFocusFilterRow")
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)

        focus_badge = QLabel("沉浸模式")
        focus_badge.setObjectName("immersiveModeBadge")
        filter_layout.addWidget(focus_badge, 0)

        filter_edit = QLineEdit()
        filter_edit.setClearButtonEnabled(True)
        filter_edit.setPlaceholderText("筛选 名称 / 地址 / 注释 / 机架 / 使用  (Ctrl+Shift+F)")
        filter_edit.textChanged.connect(lambda _text, current=table: self._apply_editor_filter(current))
        filter_layout.addWidget(filter_edit, 1)
        focus_layout.addWidget(filter_row, 0)

        action_row = QWidget(focus_bar)
        action_row.setObjectName("immersiveFocusActionsRow")
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        filled_toggle = _make_immersive_btn("只看有内容")
        filled_toggle.setCheckable(True)
        filled_toggle.toggled.connect(lambda _checked, current=table: self._apply_editor_filter(current))
        action_layout.addWidget(filled_toggle, 0)

        btn_clear_filter = _make_immersive_btn("清空筛选")
        btn_insert_above = _make_immersive_btn("上插", icon_name="add-light")
        btn_insert_below = _make_immersive_btn("下插", icon_name="add-light")
        btn_duplicate = _make_immersive_btn("复制选中", icon_name="clipboard-light")
        btn_delete_rows = _make_immersive_btn("删除选中", danger=True, icon_name="trash-light")
        btn_clear_filter.clicked.connect(lambda: filter_edit.clear())
        btn_insert_above.clicked.connect(lambda: self._insert_row_in(table, below=False))
        btn_insert_below.clicked.connect(lambda: self._insert_row_in(table, below=True))
        btn_duplicate.clicked.connect(lambda: self._duplicate_rows_in(table))
        btn_delete_rows.clicked.connect(lambda: self._del_rows_in(table))
        for button in (btn_clear_filter, btn_insert_above, btn_insert_below, btn_duplicate, btn_delete_rows):
            action_layout.addWidget(button, 0)
        action_layout.addStretch(1)
        focus_layout.addWidget(action_row, 0)

        table_shell_layout.addWidget(tools_bar, 0)
        table_shell_layout.addWidget(focus_bar, 0)
        table_shell_layout.addWidget(table, 1)
        outer_h.addWidget(table_shell, 1)

        # 右侧信息面板
        side_panel = QWidget()
        side_panel.setObjectName("editorSidePanel")
        side_panel.setHidden(self._immersive_mode)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)

        zone_panel = ZoneInfoPanel()
        zone_panel.set_zone_by_id(zone_id)
        side_layout.addWidget(zone_panel, 0, Qt.AlignmentFlag.AlignTop)
        side_layout.addStretch(1)
        outer_h.addWidget(side_panel, 0)

        self._editor_focus_bars[table] = focus_bar
        self._editor_side_panels[table] = side_panel
        self._editor_filter_edits[table] = filter_edit
        self._editor_filled_toggles[table] = filled_toggle

        return outer, table

    def _capture_project_workspace_state(self) -> None:
        if self._tabs is None:
            return
        state = dict(self._project.workspace_state or {})
        current_index = self._tabs.currentIndex()
        if current_index <= 0:
            state["active_tab"] = PREVIEW_LABEL
        elif current_index - 1 < len(self._project.channels):
            state["active_tab"] = self._project.channels[current_index - 1].name
        if self._preview_list is not None:
            state["preview_order"] = [
                self._preview_list.item(index).text()
                for index in range(self._preview_list.count())
            ]
            state["preview_checked"] = [
                self._preview_list.item(index).text()
                for index in range(self._preview_list.count())
                if self._preview_list.item(index).checkState() == Qt.CheckState.Checked
            ]
        if self._channel_tables:
            state["table_layout"] = self._channel_tables[0].layout_state()
        filters: dict[str, dict[str, object]] = {}
        for index, table in enumerate(self._channel_tables):
            if index >= len(self._project.channels):
                continue
            filters[self._project.channels[index].name] = {
                "query": self._editor_filter_edits[table].text(),
                "filled_only": self._editor_filled_toggles[table].isChecked(),
            }
        state["filters"] = filters
        state["immersive_mode"] = self._immersive_mode
        state["workspace_mode"] = self._workspace_mode
        if self._program_workspace is not None:
            self._program_workspace.commit_to_project()
            state["program_workspace"] = self._program_workspace.capture_state()
        self._project.workspace_state = state

    def _apply_project_workspace_state(self, fallback_index: int = 1) -> int:
        state = self._project_view_state()
        self._restoring_workspace = True
        try:
            if self._program_workspace is not None:
                self._program_workspace.set_project(self._project)
            self._restore_preview_workspace_state(state)
            table_layout = state.get("table_layout")
            if not isinstance(table_layout, dict) or not table_layout:
                table_layout = (
                    self._project.project_preferences.get("column_layout")
                    or self._global_editor_defaults().get("default_column_layout")
                    or {}
                )
            if isinstance(table_layout, dict):
                for table in self._channel_tables:
                    table.apply_layout_state(table_layout)
            filters = state.get("filters")
            if isinstance(filters, dict):
                for index, table in enumerate(self._channel_tables):
                    if index >= len(self._project.channels):
                        continue
                    channel_name = self._project.channels[index].name
                    filter_state = filters.get(channel_name, {})
                    if not isinstance(filter_state, dict):
                        continue
                    self._editor_filter_edits[table].setText(str(filter_state.get("query", "") or ""))
                    self._editor_filled_toggles[table].setChecked(bool(filter_state.get("filled_only", False)))
            immersive_mode = bool(
                state.get(
                    "immersive_mode",
                    self._effective_editor_defaults().get("default_immersive", False),
                )
            )
            self._set_immersive_mode(immersive_mode)
            self._set_workspace_mode(str(state.get("workspace_mode", "io") or "io"))
            active_tab = str(state.get("active_tab", "") or "")
            if _is_preview_tab_label(active_tab):
                return 0
            for index, channel in enumerate(self._project.channels, start=1):
                if channel.name == active_tab:
                    return index
        finally:
            self._restoring_workspace = False
        return max(0, min(fallback_index, self._tabs.count() - 1 if self._tabs is not None else 0))

    # ── Tab 管理 ──────────────────────────────────────────────────────────

    def _rebuild_tabs(self, select_index: int = 0) -> None:
        with self._suspend_visible_updates():
            self._building_tabs = True
            self._flush_all_channel_tables()
            assert self._tabs is not None
            while self._tabs.count():
                self._tabs.removeTab(0)
            self._channel_tables.clear()
            self._editor_focus_bars.clear()
            self._editor_side_panels.clear()
            self._editor_filter_edits.clear()
            self._editor_filled_toggles.clear()

            self._tabs.addTab(self._build_preview_tab(), PREVIEW_LABEL)

            for ch in self._project.channels:
                w, tbl = self._make_channel_editor(ch.zone_id)
                self._channel_tables.append(tbl)
                self._load_table_from_points(tbl, ch.points)
                tab_idx = self._tabs.addTab(w, ch.name)
                self._color_tab(tab_idx, ch.zone_id)

            self._sync_preview_channel_list()
            if self._program_workspace is not None:
                self._program_workspace.set_project(self._project)
            self._building_tabs = False
            self._preview_dirty = True
            self._prev_tab_index = None
            idx = self._apply_project_workspace_state(select_index)
            idx = max(0, min(idx, self._tabs.count() - 1))
            self._tabs.setCurrentIndex(idx)
            self._prev_tab_index = idx
            self._sync_channel_action_buttons()
            if idx == 0:
                self._ensure_preview_fresh()
            self._refresh_validation_panel()
            self._install_resize_watchers(self)

    def _sync_channel_action_buttons(self) -> None:
        if self._tabs is None:
            return
        current_index = self._tabs.currentIndex()
        can_delete = current_index > 0 and len(self._project.channels) > 1
        if self._btn_enter_immersive is not None:
            self._btn_enter_immersive.setEnabled(True)
        self._btn_add_ch.setEnabled(True)
        self._btn_del_ch.setEnabled(can_delete)
        if current_index <= 0:
            self._btn_del_ch.setToolTip("切换到具体分区后可删除当前分区")
        elif len(self._project.channels) <= 1:
            self._btn_del_ch.setToolTip("至少保留一个分区")
        else:
            self._btn_del_ch.setToolTip("删除当前选中分区（至少保留一个）")

    def _color_tab(self, tab_index: int, zone_id: str) -> None:
        if not self._tabs:
            return
        zone = get_zone(zone_id) if zone_id else None
        if zone:
            self._tabs.tabBar().setTabTextColor(tab_index, QColor(zone.color))

    def _load_table_from_points(self, table: IoTableWidget, points: list[IoPoint]) -> None:
        table.blockSignals(True)
        table.setRowCount(0)
        for p in points:
            self._append_row_from_point(table, p)
        table._ensure_spare_rows()
        table.blockSignals(False)

    def _append_row_from_point(self, table: IoTableWidget, p: IoPoint) -> None:
        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, COL_NAME,    QTableWidgetItem(p.name))
        table.setItem(r, COL_DTYPE,   QTableWidgetItem(p.data_type or "BOOL"))
        table.setItem(r, COL_ADDR,    QTableWidgetItem(p.address))
        table.setItem(r, COL_COMMENT, QTableWidgetItem(p.comment))
        table.setItem(r, COL_RACK,    QTableWidgetItem(p.rack))
        table.setItem(r, COL_USAGE,   QTableWidgetItem(p.usage))

    def _add_row_to(self, table: IoTableWidget) -> None:
        table._insert_row(below=True)
        table.setCurrentCell(max(0, table.currentRow()), COL_NAME)

    def _insert_row_in(self, table: IoTableWidget, below: bool) -> None:
        table._insert_row(below=below)
        table.setFocus()

    def _duplicate_rows_in(self, table: IoTableWidget) -> None:
        table.duplicate_selected_rows()
        table.setFocus()

    def _del_rows_in(self, table: IoTableWidget) -> None:
        table._delete_selected_rows()

    def _open_batch_generate(self, table: IoTableWidget) -> None:
        dialog = BatchGenerateDialog(defaults=self._project_generation_defaults(), parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._apply_batch_generate(table, dialog.values())

    def _apply_batch_generate(self, table: IoTableWidget, spec: dict[str, object]) -> None:
        row_count = max(1, int(spec.get("row_count", 1) or 1))
        start_address = str(spec.get("start_address", "") or "").strip()
        data_type = str(spec.get("data_type", "BOOL") or "BOOL").strip() or "BOOL"
        name_template = str(spec.get("name_template", "") or "")
        comment_template = str(spec.get("comment_template", "") or "")
        rack = str(spec.get("rack", "") or "")
        usage = str(spec.get("usage", "") or "")

        start_row = table.currentRow() if table.currentRow() >= 0 else 0
        changes: list[tuple[int, int, str, str]] = []
        current_address = start_address
        for offset in range(row_count):
            row = start_row + offset
            table._ensure_row_available(row)
            address = current_address if current_address else ""
            values = {
                COL_NAME: _render_generation_template(name_template, offset, address),
                COL_DTYPE: data_type,
                COL_ADDR: address,
                COL_COMMENT: _render_generation_template(comment_template, offset, address),
                COL_RACK: rack,
                COL_USAGE: usage,
            }
            for col, new_value in values.items():
                old = table.item(row, col).text() if table.item(row, col) else ""
                if old != new_value:
                    changes.append((row, col, old, new_value))
            if current_address:
                current_address = _next_address_value(current_address)
        table.apply_multi_changes(changes, "批量生成", "generate")
        self._sync_table_to_project(table)
        self._set_modified(True)
        self._schedule_preview_refresh()

    def _open_bulk_row_update(self, table: IoTableWidget) -> None:
        if not table.selected_row_numbers():
            self._show_toast("批量设置", "请先点击左侧行号，选择一行或多行后再执行批量设置。", "info")
            return
        dialog = BulkRowUpdateDialog(parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = {key: value for key, value in dialog.values().items() if value}
        if not values:
            return
        table.bulk_update_selected_rows(values)
        self._sync_table_to_project(table)
        self._set_modified(True)
        self._schedule_preview_refresh()

    def _open_bulk_text_transform(self, table: IoTableWidget, mode: str) -> None:
        if not table.selectedIndexes() and not table.currentIndex().isValid():
            self._show_toast("批量文本处理", "请先选中要处理的单元格，再执行批量文本操作。", "info")
            return
        if mode == "number":
            value, ok = self._dialog_int("批量加编号", "起始编号：", 1, 1, 9999)
            if not ok:
                return
            table.bulk_transform_selection("number", start=value)
        else:
            title = "批量加前缀" if mode == "prefix" else "批量加后缀"
            label = "请输入前缀：" if mode == "prefix" else "请输入后缀："
            text, ok = self._dialog_text(title, label)
            if not ok or not text:
                return
            table.bulk_transform_selection(mode, text)
        self._sync_table_to_project(table)
        self._set_modified(True)
        self._schedule_preview_refresh()

    def _show_batch_edit_guide(self) -> None:
        self._dialog_message(
            "批量编辑说明",
            "\n".join(
                [
                    "1. 批量生成：把光标放到起始行，按模板连续生成多行。",
                    "2. 批量设置：先点击左侧行号选中一行或多行，再统一改数据类型、机架位置、使用。",
                    "3. 加前缀/加后缀/加编号：先选中要处理的单元格区域，只会改已有文本。",
                    "4. 所有批量操作都进入撤销栈，可直接使用 Ctrl+Z 撤回。",
                ]
            ),
            buttons=("知道了",),
        )

    def _current_channel_table(self) -> IoTableWidget | None:
        if self._tabs is None:
            return None
        idx = self._tabs.currentIndex() - 1
        if idx < 0 or idx >= len(self._channel_tables):
            return None
        return self._channel_tables[idx]

    def _row_matches_query(self, table: IoTableWidget, row: int, query: str) -> bool:
        if not query:
            return True
        parts: list[str] = []
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item and item.text().strip():
                parts.append(item.text())
        return query in " ".join(parts).casefold()

    def _clear_editor_row_filter(self, table: IoTableWidget) -> None:
        for row in range(table.rowCount()):
            table.setRowHidden(row, False)

    def _apply_editor_filter(self, table: IoTableWidget) -> None:
        if table not in self._editor_filter_edits:
            return
        if not self._immersive_mode:
            self._clear_editor_row_filter(table)
            return
        query = self._editor_filter_edits[table].text().strip().casefold()
        filled_only = self._editor_filled_toggles[table].isChecked()
        for row in range(table.rowCount()):
            has_content = table.row_has_content(row)
            visible = True
            if filled_only and not has_content:
                visible = False
            if query:
                visible = has_content and self._row_matches_query(table, row, query)
            elif not has_content and filled_only:
                visible = False
            table.setRowHidden(row, not visible)

    def _focus_current_editor_filter(self) -> None:
        table = self._current_channel_table()
        if table is None:
            return
        if not self._immersive_mode:
            self._set_immersive_mode(True)
        editor = self._editor_filter_edits.get(table)
        if editor is None:
            return
        editor.setFocus()
        editor.selectAll()

    def _sync_immersive_corner_button(self) -> None:
        if self._btn_enter_immersive is None:
            return
        if self._immersive_mode:
            self._btn_enter_immersive.setText("退出沉浸")
            self._btn_enter_immersive.setToolTip("退出沉浸模式，返回标准编辑界面")
        else:
            self._btn_enter_immersive.setText("进入沉浸")
            self._btn_enter_immersive.setToolTip("聚焦当前分区编辑画布")

    def _sync_workspace_mode_buttons(self) -> None:
        if self._btn_workspace_io is not None:
            self._btn_workspace_io.setChecked(self._workspace_mode == "io")
        if self._btn_workspace_program is not None:
            self._btn_workspace_program.setChecked(self._workspace_mode == "program")
        if self._immersive_action is not None:
            self._immersive_action.setEnabled(self._workspace_mode == "io")

    def _set_workspace_mode(self, mode: str) -> None:
        mode = "program" if mode == "program" else "io"
        if mode == "program" and self._immersive_mode:
            self._set_immersive_mode(False)
        self._workspace_mode = mode
        if self._workspace_stack is not None:
            self._workspace_stack.setCurrentIndex(1 if mode == "program" else 0)
        self._sync_workspace_mode_buttons()
        if self._program_workspace is not None and mode == "program":
            self._program_workspace.set_project(self._project)

    def _set_immersive_mode(self, enabled: bool) -> None:
        if self._workspace_mode != "io":
            enabled = False
        enabled = bool(enabled)
        self._immersive_mode = enabled
        if self._immersive_action is not None and self._immersive_action.isChecked() != enabled:
            self._immersive_action.blockSignals(True)
            self._immersive_action.setChecked(enabled)
            self._immersive_action.blockSignals(False)
        self._sync_immersive_corner_button()
        prefs = _get_prefs()
        startup_prefs = prefs.startup_preferences() if hasattr(prefs, "startup_preferences") else {}
        if self._sidebar is not None:
            self._sidebar.setHidden(enabled)
        for widget in (self._project_meta_group, self._copy_group, self._toolbar):
            if widget is not None:
                widget.setHidden(enabled)
        if self._recent_group is not None:
            self._recent_group.setHidden(enabled or not bool(startup_prefs.get("show_recent_sidebar", True)))
        for table, focus_bar in self._editor_focus_bars.items():
            focus_bar.setHidden(not enabled)
            side_panel = self._editor_side_panels.get(table)
            if side_panel is not None:
                side_panel.setHidden(enabled)
            if enabled:
                self._apply_editor_filter(table)
            else:
                self._clear_editor_row_filter(table)
        if enabled:
            self.statusBar().showMessage("沉浸模式已开启 · Ctrl+F 查找 · Ctrl+Shift+F 筛选当前分区 · F11 退出", 4000)
        else:
            self.statusBar().showMessage("已退出沉浸模式", 2500)

    def _read_points_from_table(self, table: IoTableWidget) -> list[IoPoint]:
        pts: list[IoPoint] = []
        for r in range(table.rowCount()):
            nm      = table.item(r, COL_NAME)
            dt      = table.item(r, COL_DTYPE)
            addr    = table.item(r, COL_ADDR)
            comment = table.item(r, COL_COMMENT)
            rack    = table.item(r, COL_RACK)
            usage   = table.item(r, COL_USAGE)
            name_s  = (nm.text() if nm else "").strip()
            addr_s  = (addr.text() if addr else "").strip()
            if not name_s and not addr_s:
                continue
            pts.append(
                IoPoint(
                    name=name_s,
                    data_type=(dt.text() if dt else "BOOL").strip() or "BOOL",
                    address=addr_s,
                    comment=(comment.text() if comment else "").strip(),
                    rack=(rack.text() if rack else "").strip(),
                    usage=(usage.text() if usage else "").strip(),
                )
            )
        return pts

    def _channel_index_for_table(self, table: IoTableWidget) -> int | None:
        try:
            return self._channel_tables.index(table)
        except ValueError:
            return None

    def _sync_table_to_project(self, table: IoTableWidget) -> None:
        ci = self._channel_index_for_table(table)
        if ci is None:
            return
        self._project.channels[ci].points = self._read_points_from_table(table)

    def _on_channel_table_dirty(self, table: IoTableWidget, _reason: str) -> None:
        if self._building_tabs or self._restoring_workspace:
            return
        if self._immersive_mode:
            self._apply_editor_filter(table)
        self._sync_table_to_project(table)
        self._set_modified(True)
        self._schedule_preview_refresh()
        self._schedule_validation_refresh()

    def _flush_all_channel_tables(self) -> None:
        for i, tbl in enumerate(self._channel_tables):
            tbl.flush_active_editor()
            if i < len(self._project.channels):
                self._project.channels[i].points = self._read_points_from_table(tbl)

    def _on_tab_changed(self, idx: int) -> None:
        if self._building_tabs or self._tabs is None:
            return
        self._prev_tab_index = idx
        self._sync_channel_action_buttons()
        if idx == 0:
            self._sync_preview_channel_list()
            self._ensure_preview_fresh()
        elif self._immersive_mode:
            table = self._current_channel_table()
            if table is not None:
                self._apply_editor_filter(table)

    def _on_tab_bar_double_clicked(self, index: int) -> None:
        if index <= 0 or index >= self._tabs.count():
            return
        ci = index - 1
        old = self._project.channels[ci].name
        text, ok = self._dialog_text("重命名分区", "分区名称：", old)
        if not ok or not text.strip():
            return
        new_name = text.strip()
        if new_name != old and any(c.name == new_name for c in self._project.channels):
            self._dialog_warning("重命名", "已存在同名分区。")
            return
        self._project.channels[ci].name = new_name
        self._tabs.setTabText(index, new_name)
        self._sync_preview_channel_list()
        self._schedule_preview_refresh(immediate=self._tabs.currentIndex() == 0)
        self._set_modified(True)

    def _add_channel(self) -> None:
        self._flush_all_channel_tables()
        existing_ids = {ch.zone_id for ch in self._project.channels if ch.zone_id}
        from omron_io_planner.ui import main_window as _mw
        ZonePickerDialog = _mw.ZonePickerDialog
        dlg = ZonePickerDialog(existing_ids, self)
        if dlg.exec() != ZonePickerDialog.DialogCode.Accepted:
            return

        zone_ids = list(dlg.result_zone_ids)
        custom_name = dlg.result_custom_name
        added_any = False

        if custom_name:
            name = custom_name or self._project.unique_channel_name()
            if any(c.name == name for c in self._project.channels):
                self._dialog_warning("添加分区", f"已存在名称为「{name}」的分区。")
                return
            zone_ids = [""]

        assert self._tabs is not None
        for zone_id in zone_ids:
            if zone_id:
                zone = get_zone(zone_id)
                assert zone is not None
                name = zone.display_name
            else:
                name = custom_name or self._project.unique_channel_name()

            if any(c.name == name for c in self._project.channels):
                continue

            new_ch = IoChannel(name=name, zone_id=zone_id, points=[])
            self._project.channels.append(new_ch)
            w, tbl = self._make_channel_editor(zone_id)
            self._channel_tables.append(tbl)
            tab_idx = self._tabs.addTab(w, name)
            self._color_tab(tab_idx, zone_id)
            if self._immersive_mode:
                self._apply_editor_filter(tbl)
            added_any = True

        if not added_any:
            return

        self._sync_preview_channel_list()
        self._schedule_preview_refresh()
        self._tabs.setCurrentIndex(self._tabs.count() - 1)
        self._set_modified(True)
        self._install_resize_watchers(self)

    def _delete_current_channel(self) -> None:
        assert self._tabs is not None
        idx = self._tabs.currentIndex()
        if idx <= 0:
            self._dialog_info("删除分区", "请先切换到要删除的分区选项卡。")
            return
        if len(self._project.channels) <= 1:
            self._dialog_warning("删除分区", "至少保留一个分区。")
            return
        ci   = idx - 1
        name = self._project.channels[ci].name
        if self._dialog_message("确认删除", f"删除分区「{name}」及其全部 IO 点？", buttons=("删除", "取消")) != "删除":
            return
        self._flush_all_channel_tables()
        self._project.channels.pop(ci)
        self._rebuild_tabs(select_index=max(1, idx - 1))
        self._set_modified(True)
