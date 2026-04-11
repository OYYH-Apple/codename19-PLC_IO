# -*- coding: utf-8 -*-
"""主窗口：全通道预览与轻量校验面板（Mixin）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..omron_zones import get_zone
from .main_window_constants import (
    COL_NAME,
    PREVIEW_COLUMN_WIDTH_LIMITS as _PREVIEW_COLUMN_WIDTH_LIMITS,
    PREVIEW_TABLE_HEADERS as _PREVIEW_TABLE_HEADERS,
    VALID_DATA_TYPES as _VALID_DATA_TYPES,
)
from .main_window_utils import _make_action_btn


class MainWindowPreviewValidationMixin:
    """依赖 MainWindow 在 __init__ 中已创建定时器与状态字段。"""

    _building_tabs: bool
    _restoring_workspace: bool
    _preview_list: QListWidget | None
    _preview_table: QTableWidget | None
    _preview_sidebar: QWidget | None
    _preview_actions: QWidget | None
    _preview_row_links: list[tuple[int, int]]
    _preview_dirty: bool
    _tabs: QTabWidget | None
    _preview_refresh_timer: QTimer
    _validation_refresh_timer: QTimer
    _validation_issues: list[dict[str, object]]
    _validation_list: QListWidget | None
    _validation_group: QGroupBox | None
    _validation_body: QWidget | None
    _validation_toggle_btn: QPushButton | None
    _validation_summary_label: QLabel | None
    _validation_collapsed: bool
    _channel_tables: list
    _project: object

    def _build_preview_tab(self) -> QWidget:
        w = QWidget()
        root = QHBoxLayout(w)
        root.setSpacing(12)
        root.setContentsMargins(8, 8, 8, 8)

        self._preview_sidebar = QWidget(w)
        self._preview_sidebar.setObjectName("previewSidebar")
        self._preview_sidebar.setMaximumWidth(260)
        self._preview_sidebar.setMinimumWidth(220)
        side = QVBoxLayout(self._preview_sidebar)
        side.setSpacing(10)
        side.setContentsMargins(0, 0, 0, 0)

        hint = QLabel("勾选要参与预览拼接的分区；列表可上下拖拽调整拼接顺序。")
        hint.setStyleSheet("color: #5A6080; font-size: 9pt;")
        hint.setWordWrap(True)
        side.addWidget(hint)

        self._preview_list = QListWidget()
        self._preview_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._preview_list.itemChanged.connect(self._on_preview_item_changed)
        _pm = self._preview_list.model()
        if hasattr(_pm, "rowsMoved"):
            _pm.rowsMoved.connect(lambda *_: self._schedule_preview_refresh(immediate=True))
        side.addWidget(self._preview_list, 1)

        self._preview_actions = QWidget(self._preview_sidebar)
        h = QHBoxLayout(self._preview_actions)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        b_all = _make_action_btn("全选", compact=True)
        b_none = _make_action_btn("全不选", compact=True)
        b_refresh = _make_action_btn("刷新预览", compact=True)
        for button in (b_all, b_none, b_refresh):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b_all.clicked.connect(self._preview_check_all)
        b_none.clicked.connect(self._preview_check_none)
        b_refresh.clicked.connect(self._refresh_preview_table)
        for button in (b_all, b_none, b_refresh):
            h.addWidget(button, 1)
        side.addWidget(self._preview_actions)

        self._preview_table = QTableWidget(0, 7)
        self._preview_table.setHorizontalHeaderLabels(_PREVIEW_TABLE_HEADERS)
        self._preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview_table.setAlternatingRowColors(True)
        self._preview_table.itemDoubleClicked.connect(self._on_preview_item_double_clicked)
        self._preview_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root.addWidget(self._preview_sidebar, 0)
        root.addWidget(self._preview_table, 1)
        return w

    def _on_preview_item_changed(self, _item: QListWidgetItem) -> None:
        if self._building_tabs or self._restoring_workspace:
            return
        self._schedule_preview_refresh(immediate=True)
        self._schedule_validation_refresh()

    def _preview_check_all(self) -> None:
        if not self._preview_list:
            return
        self._preview_list.blockSignals(True)
        for i in range(self._preview_list.count()):
            self._preview_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._preview_list.blockSignals(False)
        self._schedule_preview_refresh(immediate=True)
        self._schedule_validation_refresh()

    def _preview_check_none(self) -> None:
        if not self._preview_list:
            return
        self._preview_list.blockSignals(True)
        for i in range(self._preview_list.count()):
            self._preview_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._preview_list.blockSignals(False)
        self._schedule_preview_refresh(immediate=True)
        self._schedule_validation_refresh()

    def _sync_preview_channel_list(self) -> None:
        if not self._preview_list:
            return
        checked: dict[str, bool] = {}
        for i in range(self._preview_list.count()):
            it = self._preview_list.item(i)
            checked[it.text()] = it.checkState() == Qt.CheckState.Checked
        self._preview_list.blockSignals(True)
        self._preview_list.clear()
        for ch in self._project.channels:
            item = QListWidgetItem(ch.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if checked.get(ch.name, True) else Qt.CheckState.Unchecked
            )
            zone = get_zone(ch.zone_id) if ch.zone_id else None
            if zone:
                item.setForeground(QColor(zone.color))
            self._preview_list.addItem(item)
        self._preview_list.blockSignals(False)

    def _selected_preview_channel_order(self) -> list[str]:
        if not self._preview_list:
            return [c.name for c in self._project.channels]
        names: list[str] = []
        for i in range(self._preview_list.count()):
            it = self._preview_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                names.append(it.text())
        return names

    def _autosize_preview_columns(self) -> None:
        if not self._preview_table:
            return
        table = self._preview_table
        header = table.horizontalHeader()
        for col in range(table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            table.resizeColumnToContents(col)
            measured = max(table.columnWidth(col), header.sectionSizeHint(col)) + 18
            min_width, max_width = _PREVIEW_COLUMN_WIDTH_LIMITS.get(col, (96, 260))
            table.setColumnWidth(col, max(min_width, min(max_width, measured)))

    def _refresh_preview_table(self) -> None:
        if self._building_tabs or not self._preview_table:
            return
        self._preview_dirty = False
        self._preview_row_links = []
        names = self._selected_preview_channel_order()
        self._preview_table.setRowCount(0)
        by_name = {channel.name: (index, channel) for index, channel in enumerate(self._project.channels)}
        for channel_name in names:
            channel_info = by_name.get(channel_name)
            if channel_info is None:
                continue
            channel_index, channel = channel_info
            for point_index, point in enumerate(channel.points):
                row = self._preview_table.rowCount()
                self._preview_table.insertRow(row)
                values = [
                    channel.name,
                    point.name,
                    point.data_type,
                    point.address,
                    point.comment,
                    point.rack,
                    point.usage,
                ]
                for col, value in enumerate(values):
                    self._preview_table.setItem(row, col, QTableWidgetItem(str(value)))
                self._preview_row_links.append((channel_index, point_index))
        self._autosize_preview_columns()

    def _schedule_preview_refresh(self, immediate: bool = False) -> None:
        if self._building_tabs:
            return
        self._preview_dirty = True
        if self._tabs and self._tabs.currentIndex() == 0:
            if immediate:
                self._preview_refresh_timer.stop()
                self._refresh_preview_table()
            else:
                self._preview_refresh_timer.start()

    def _ensure_preview_fresh(self) -> None:
        if self._preview_dirty:
            self._preview_refresh_timer.stop()
            self._refresh_preview_table()

    def _schedule_validation_refresh(self) -> None:
        if self._building_tabs or self._restoring_workspace:
            return
        self._validation_refresh_timer.start()

    def _collect_validation_issues(self) -> list[dict[str, object]]:
        issues: list[dict[str, object]] = []
        seen_addresses: dict[tuple[str, str], tuple[int, int]] = {}
        seen_names: dict[str, tuple[int, int]] = {}
        for channel_index, channel in enumerate(self._project.channels):
            zone_id = channel.zone_id.strip()
            address_scope = f"zone:{zone_id}" if zone_id else f"channel:{channel_index}"
            for row_index, point in enumerate(channel.points):
                name = point.name.strip()
                if name:
                    prior_name = seen_names.get(name)
                    if prior_name is not None:
                        issues.append(
                            {
                                "code": "duplicate_name",
                                "message": f"{channel.name} / 第 {row_index + 1} 行名称重复：{name}",
                                "channel_index": channel_index,
                                "row_index": row_index,
                            }
                        )
                    else:
                        seen_names[name] = (channel_index, row_index)
                address = point.address.strip()
                if address:
                    address_key = (address_scope, address)
                    prior = seen_addresses.get(address_key)
                    if prior is not None:
                        issues.append(
                            {
                                "code": "duplicate_address",
                                "message": f"{channel.name} / 第 {row_index + 1} 行地址重复：{address}",
                                "channel_index": channel_index,
                                "row_index": row_index,
                            }
                        )
                    else:
                        seen_addresses[address_key] = (channel_index, row_index)
                if point.data_type.strip().upper() not in _VALID_DATA_TYPES:
                    issues.append(
                        {
                            "code": "invalid_data_type",
                            "message": f"{channel.name} / 第 {row_index + 1} 行数据类型无效：{point.data_type}",
                            "channel_index": channel_index,
                            "row_index": row_index,
                        }
                    )
        if not self._selected_preview_channel_order():
            issues.append(
                {
                    "code": "empty_preview",
                    "message": "全通道预览未勾选任何分区",
                    "channel_index": -1,
                    "row_index": -1,
                }
            )
        return issues

    def _refresh_validation_panel(self) -> None:
        self._validation_issues = self._collect_validation_issues()
        if self._validation_list is None or self._validation_group is None:
            return
        self._validation_list.clear()
        for issue in self._validation_issues:
            item = QListWidgetItem(str(issue["message"]))
            item.setData(Qt.ItemDataRole.UserRole, issue)
            self._validation_list.addItem(item)
        has_issues = bool(self._validation_issues)
        self._validation_group.setTitle(f"轻量校验（{len(self._validation_issues)}）")
        self._validation_group.setHidden(not has_issues)
        if self._validation_body is not None:
            self._validation_body.setHidden(self._validation_collapsed or not has_issues)
        if self._validation_toggle_btn is not None:
            self._validation_toggle_btn.setHidden(not has_issues)
            self._validation_toggle_btn.setText("展开详情" if self._validation_collapsed else "收起详情")
        if self._validation_summary_label is not None:
            summary = ""
            if has_issues and self._validation_collapsed:
                summary = f"已折叠，当前 {len(self._validation_issues)} 项；首项：{self._validation_issues[0]['message']}"
            self._validation_summary_label.setText(summary)
            self._validation_summary_label.setVisible(bool(summary))

    def _jump_to_validation_issue(self, item: QListWidgetItem) -> None:
        issue = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(issue, dict):
            return
        channel_index = int(issue.get("channel_index", -1))
        row_index = int(issue.get("row_index", -1))
        if issue.get("code") == "empty_preview":
            if self._tabs is not None:
                self._tabs.setCurrentIndex(0)
            return
        if channel_index < 0 or channel_index >= len(self._channel_tables) or self._tabs is None:
            return
        self._tabs.setCurrentIndex(channel_index + 1)
        table = self._channel_tables[channel_index]
        if 0 <= row_index < table.rowCount():
            table.setCurrentCell(row_index, COL_NAME)
            table.scrollToItem(table.item(row_index, COL_NAME))

    def _toggle_validation_panel(self) -> None:
        if not self._validation_issues:
            return
        self._validation_collapsed = not self._validation_collapsed
        if self._validation_body is not None:
            self._validation_body.setHidden(self._validation_collapsed)
        if self._validation_toggle_btn is not None:
            self._validation_toggle_btn.setText("展开详情" if self._validation_collapsed else "收起详情")
        if self._validation_summary_label is not None:
            if self._validation_collapsed and self._validation_issues:
                self._validation_summary_label.setText(
                    f"已折叠，当前 {len(self._validation_issues)} 项；首项：{self._validation_issues[0]['message']}"
                )
                self._validation_summary_label.show()
            else:
                self._validation_summary_label.hide()

    def _confirm_export_validation(self) -> bool:
        issues = self._collect_validation_issues()
        if not issues:
            return True
        summary = "\n".join(f"• {issue['message']}" for issue in issues[:3])
        choice = self._dialog_message(
            "导出前检查",
            f"检测到 {len(issues)} 个潜在问题：\n{summary}\n\n是否继续导出？",
            buttons=("查看问题", "继续导出", "取消"),
        )
        if choice == "查看问题" and self._validation_list is not None and self._validation_list.count():
            self._jump_to_validation_issue(self._validation_list.item(0))
            return False
        return choice == "继续导出"

    def _on_preview_item_double_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if row < 0 or row >= len(self._preview_row_links) or self._tabs is None:
            return
        channel_index, point_index = self._preview_row_links[row]
        if channel_index >= len(self._channel_tables):
            return
        self._tabs.setCurrentIndex(channel_index + 1)
        table = self._channel_tables[channel_index]
        table.setCurrentCell(point_index, COL_NAME)
        table.scrollToItem(table.item(point_index, COL_NAME))

    def _restore_preview_workspace_state(self, state: dict[str, object]) -> None:
        if self._preview_list is None:
            return
        preferred_order = [str(name) for name in state.get("preview_order", []) if str(name)]
        preferred_checked = {str(name) for name in state.get("preview_checked", []) if str(name)}
        existing = []
        for index in range(self._preview_list.count()):
            item = self._preview_list.item(index)
            existing.append(
                {
                    "name": item.text(),
                    "checked": item.checkState(),
                    "color": item.foreground(),
                }
            )
        by_name = {entry["name"]: entry for entry in existing}
        ordered_names = [name for name in preferred_order if name in by_name]
        ordered_names.extend(entry["name"] for entry in existing if entry["name"] not in ordered_names)
        self._preview_list.blockSignals(True)
        self._preview_list.clear()
        for name in ordered_names:
            entry = by_name[name]
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setForeground(entry["color"])
            item.setCheckState(
                Qt.CheckState.Checked
                if name in preferred_checked
                else Qt.CheckState.Unchecked if preferred_checked else entry["checked"]
            )
            self._preview_list.addItem(item)
        self._preview_list.blockSignals(False)
