# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..export import (
    combined_export_text,
    csv_from_rows,
    rows_cio_word_index_for_points,
    rows_d_channel_for_points,
    rows_io_preview_stitched,
    rows_io_table,
    rows_io_table_channel,
    rows_symbol_table_for_points,
    stitched_points,
    tsv_from_rows,
)
from ..io_excel import import_flat_table, import_io_sheet, save_project_excel
from ..models import IoChannel, IoPoint, IoProject
from ..omron_zones import ALL_ZONES, get_zone
from ..persistence import load_project_json, save_project_json
from ..project_manager import (
    autosave,
    autosave_exists,
    autosave_mtime,
    autosave_needs_recovery,
    clear_autosave,
    get_prefs,
    load_autosave,
)
from .data_type_delegate import DataTypeDelegate
from .dialogs import (
    ChoiceInputDialog,
    IntInputDialog,
    MessageDialog,
    PreferencesDialog,
    TextInputDialog,
    ToastPopup,
)
from .icons import load_icon
from .io_table_widget import IoTableWidget
from .name_completer_delegate import NameCompleterDelegate
from .style import app_stylesheet
from .window_chrome import AppTitleBar
from .zone_info_panel import ZoneInfoPanel
from .zone_picker_dialog import ZonePickerDialog

# 列索引常量（与 IoTableWidget 保持一致）
COL_NAME    = IoTableWidget.COL_NAME
COL_DTYPE   = IoTableWidget.COL_DTYPE
COL_ADDR    = IoTableWidget.COL_ADDR
COL_COMMENT = IoTableWidget.COL_COMMENT
COL_RACK    = IoTableWidget.COL_RACK
COL_USAGE   = IoTableWidget.COL_USAGE

PREVIEW_LABEL = "📊 全通道预览"

_APP_TITLE = "欧姆龙 IO 分配助手"


def _make_action_btn(
    text: str,
    tooltip: str = "",
    danger: bool = False,
    compact: bool = False,
    icon_name: str = "",
) -> QPushButton:
    btn = QPushButton(text)
    if tooltip:
        btn.setToolTip(tooltip)
    if danger:
        btn.setProperty("danger", "true")
    if icon_name:
        btn.setIcon(load_icon(icon_name))
        btn.setIconSize(QSize(14, 14))
    if compact:
        btn.setProperty("compact", "true")
        btn.setMinimumWidth(0)
        btn.setMinimumHeight(34)
        btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    return btn


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._title_bar: AppTitleBar | None = None
        self.setObjectName("appMainWindow")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._project = IoProject(name="新项目")
        self._project_path: Path | None = None
        self._channel_tables: list[IoTableWidget] = []
        self._prev_tab_index: int | None = None
        self._building_tabs = False
        self._preview_list: QListWidget | None = None
        self._preview_table: QTableWidget | None = None
        self._preview_sidebar: QWidget | None = None
        self._preview_actions: QWidget | None = None
        self._preview_row_links: list[tuple[int, int]] = []
        self._preview_dirty = False
        self._recent_projects_list: QListWidget | None = None
        self._recent_filter_edit: QLineEdit | None = None
        self._recent_open_btn: QPushButton | None = None
        self._recent_remove_btn: QPushButton | None = None
        self._recent_clean_btn: QPushButton | None = None
        self._tabs: QTabWidget | None = None
        self._modified = False          # 未保存修改标记
        self._toast: ToastPopup | None = None

        self.setWindowTitle(_APP_TITLE)
        self.resize(1380, 860)
        self.setStyleSheet(app_stylesheet())

        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(150)
        self._preview_refresh_timer.timeout.connect(self._refresh_preview_table)

        self._autosave_recovery_timer = QTimer(self)
        self._autosave_recovery_timer.setSingleShot(True)
        self._autosave_recovery_timer.setInterval(200)
        self._autosave_recovery_timer.timeout.connect(self._check_autosave_recovery)

        self._build_ui()
        self._build_menu_toolbar()
        self._rebuild_tabs(select_index=1)

        # ── 状态栏 ──────────────────────────────────────────────────────
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_hint = QLabel(
            "双击选项卡重命名  ·  Ctrl+D 向下填充  ·  Ctrl+C/V 复制粘贴  ·  Ctrl+Z/Y 撤销/重做"
        )
        self._status_hint.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 8pt;")
        sb.addWidget(self._status_hint)

        self._autosave_label = QLabel("")
        self._autosave_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 8pt;")
        sb.addPermanentWidget(self._autosave_label)

        # ── 自动保存定时器 ───────────────────────────────────────────────
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._do_autosave)
        self._reset_autosave_timer()

        # ── 启动时检查自动保存恢复 ───────────────────────────────────────
        self._autosave_recovery_timer.start()

    # ══════════════════════════════════════════════════════════════════════════
    # 修改状态 & 标题栏
    # ══════════════════════════════════════════════════════════════════════════

    def _set_modified(self, v: bool = True) -> None:
        if self._modified == v:
            return
        self._modified = v
        self._update_title()

    def _update_title(self) -> None:
        name = self._project.name or "未命名"
        path_str = f" — {self._project_path}" if self._project_path else ""
        dot = " ●" if self._modified else ""
        self.setWindowTitle(f"{name}{dot}{path_str}  |  {_APP_TITLE}")

    def changeEvent(self, event) -> None:  # noqa: ANN001
        super().changeEvent(event)
        if self._title_bar is not None:
            self._title_bar.sync_window_state()

    def _dialog_message(
        self,
        title: str,
        text: str,
        buttons: tuple[str, ...] = ("确定",),
    ) -> str | None:
        dialog = MessageDialog(title, text, buttons=list(buttons), parent=self)
        if dialog.exec():
            return dialog.choice()
        return dialog.choice()

    def _dialog_info(self, title: str, text: str) -> None:
        self._dialog_message(title, text)

    def _dialog_warning(self, title: str, text: str) -> None:
        self._dialog_message(title, text)

    def _dialog_error(self, title: str, text: str) -> None:
        self._dialog_message(title, text)

    def _show_toast(self, title: str, text: str, kind: str = "info") -> None:
        if self._toast is None:
            self._toast = ToastPopup(self)
        self._toast.show_message(title, text, kind)

    def _dialog_text(self, title: str, label: str, text: str = "") -> tuple[str, bool]:
        return TextInputDialog.get_text(self, title, label, text)

    def _dialog_item(self, title: str, label: str, items: list[str], current_index: int = 0) -> tuple[str, bool]:
        return ChoiceInputDialog.get_item(self, title, label, items, current_index)

    def _dialog_int(
        self,
        title: str,
        label: str,
        value: int,
        minimum: int,
        maximum: int,
    ) -> tuple[int, bool]:
        return IntInputDialog.get_int(self, title, label, value, minimum, maximum)

    def _reset_autosave_timer(self) -> None:
        prefs = get_prefs()
        if prefs.autosave_enabled():
            interval_ms = prefs.autosave_interval() * 1000
            self._autosave_timer.start(interval_ms)
        else:
            self._autosave_timer.stop()

    def _do_autosave(self) -> None:
        if not self._modified:
            return
        self._flush_all_channel_tables()
        autosave(self._project, self._project_path)
        t = time.strftime("%H:%M:%S")
        self._autosave_label.setText(f"自动保存 {t}")

    def _check_autosave_recovery(self) -> None:
        """启动时检查是否有自动保存文件，询问是否恢复。"""
        if not autosave_exists():
            return
        if not autosave_needs_recovery():
            clear_autosave()
            return
        mtime = autosave_mtime()
        import datetime
        t_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        ret = self._dialog_message(
            "恢复未保存的项目",
            f"检测到上次编辑时未保存的项目（{t_str}）。\n\n是否恢复？",
            buttons=("恢复", "忽略", "清除记录"),
        )
        if ret == "恢复":
            proj = load_autosave()
            if proj:
                self._project = proj
                self._project_path = None
                # 清空表格引用，防止旧表格数据覆盖新加载的项目
                self._channel_tables.clear()
                self._sync_meta_from_project()
                self._rebuild_tabs(select_index=1)
                self._set_modified(True)
                self.statusBar().showMessage("✔ 已恢复自动保存的项目", 4000)
        elif ret == "清除记录":
            if clear_autosave() is False:
                self._dialog_warning("清除失败", "自动保存记录未能删除，请检查文件权限。")
                return
            self.statusBar().showMessage("已清除恢复记录", 3000)
            self._show_toast("恢复记录", "自动保存记录已清除", "success")

    # ══════════════════════════════════════════════════════════════════════════
    # UI 构建
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(10, 8, 10, 6)

        recent_group = QGroupBox("最近项目")
        recent_group.setObjectName("recentProjectsGroup")
        recent_group.setMaximumWidth(260)
        recent_group.setMinimumWidth(220)
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(10, 12, 10, 10)
        recent_layout.setSpacing(8)

        recent_hint = QLabel("展示最近打开或保存的项目，单击即可直接切换。")
        recent_hint.setWordWrap(True)
        recent_hint.setStyleSheet("color: #5A6080; font-size: 9pt;")
        recent_layout.addWidget(recent_hint)

        self._recent_filter_edit = QLineEdit()
        self._recent_filter_edit.setObjectName("recentProjectsFilter")
        self._recent_filter_edit.setPlaceholderText("筛选项目名称或路径")
        self._recent_filter_edit.textChanged.connect(self._filter_recent_projects_list)
        recent_layout.addWidget(self._recent_filter_edit)

        self._recent_projects_list = QListWidget()
        self._recent_projects_list.setObjectName("recentProjectsList")
        self._recent_projects_list.itemActivated.connect(self._on_recent_project_clicked)
        self._recent_projects_list.itemClicked.connect(self._on_recent_project_clicked)
        self._recent_projects_list.currentItemChanged.connect(lambda *_: self._refresh_recent_project_actions())
        recent_layout.addWidget(self._recent_projects_list, 1)

        recent_actions = QHBoxLayout()
        recent_actions.setContentsMargins(0, 0, 0, 0)
        recent_actions.setSpacing(6)
        self._recent_open_btn = _make_action_btn("打开", compact=True)
        self._recent_remove_btn = _make_action_btn("移除", compact=True)
        self._recent_clean_btn = _make_action_btn("清理失效", compact=True)
        self._recent_open_btn.clicked.connect(self._open_selected_recent_project)
        self._recent_remove_btn.clicked.connect(self._remove_selected_recent_project)
        self._recent_clean_btn.clicked.connect(self._clean_recent_projects)
        recent_actions.addWidget(self._recent_open_btn, 1)
        recent_actions.addWidget(self._recent_remove_btn, 1)
        recent_actions.addWidget(self._recent_clean_btn, 1)
        recent_layout.addLayout(recent_actions)

        root.addWidget(recent_group, 0)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(content, 1)

        # ── 项目元信息 ──────────────────────────────────────────────────────
        meta = QGroupBox("项目信息")
        form = QFormLayout(meta)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("项目名称")
        self._plc_edit = QLineEdit()
        self._plc_edit.setText(self._project.plc_prefix)
        self._plc_edit.setPlaceholderText("未命名符号前缀（如 PLC）")
        self._plc_edit.setToolTip("用于给未命名 IO 点生成默认符号名，例如 PLC_SYM_0001。已命名点不会受影响。")
        form.addRow("项目名称", self._name_edit)
        form.addRow("符号前缀", self._plc_edit)

        ch_row = QHBoxLayout()
        self._btn_add_ch = _make_action_btn("＋ 添加分区", "从标准欧姆龙分区列表选择，或添加自定义通道")
        self._btn_del_ch = _make_action_btn("－ 删除当前", "删除当前选中分区（至少保留一个）", danger=True)
        ch_row.addWidget(self._btn_add_ch)
        ch_row.addWidget(self._btn_del_ch)
        ch_row.addStretch()
        form.addRow(ch_row)
        layout.addWidget(meta)

        # ── Tab 区 ─────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        tb = self._tabs.tabBar()
        tb.tabBarDoubleClicked.connect(self._on_tab_bar_double_clicked)
        layout.addWidget(self._tabs, stretch=1)

        # ── 底部操作按钮 ────────────────────────────────────────────────────
        copy_group = QGroupBox("导出 / 复制到剪贴板")
        copy_h = QHBoxLayout(copy_group)
        copy_h.setSpacing(8)
        self._btn_copy_io   = _make_action_btn("IO 表",          "复制当前分区的 IO 表（TSV）", icon_name="clipboard-light")
        self._btn_copy_sym  = _make_action_btn("符号表",          "复制当前分区的符号表（TSV）", icon_name="clipboard-light")
        self._btn_copy_d    = _make_action_btn("D 区 CHANNEL",   "复制 D 区 CHANNEL 行", icon_name="clipboard-light")
        self._btn_copy_cio  = _make_action_btn("CIO 字 CHANNEL", "复制 CIO 字 CHANNEL 行", icon_name="clipboard-light")
        self._btn_copy_all  = _make_action_btn("合并全部分区",    "合并所有分区文本到剪贴板", icon_name="clipboard-light")
        for btn in (self._btn_copy_io, self._btn_copy_sym,
                    self._btn_copy_d, self._btn_copy_cio, self._btn_copy_all):
            copy_h.addWidget(btn)
        copy_h.addStretch()
        layout.addWidget(copy_group)

        # 连接
        self._btn_add_ch.clicked.connect(self._add_channel)
        self._btn_del_ch.clicked.connect(self._delete_current_channel)
        self._btn_copy_io.clicked.connect(self._copy_io)
        self._btn_copy_sym.clicked.connect(self._copy_symbol)
        self._btn_copy_d.clicked.connect(self._copy_d)
        self._btn_copy_cio.clicked.connect(self._copy_cio)
        self._btn_copy_all.clicked.connect(self._copy_combined)
        self._name_edit.textChanged.connect(self._on_meta_changed)
        self._plc_edit.textChanged.connect(self._on_meta_changed)

    # ── 预览 Tab ───────────────────────────────────────────────────────────

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
        b_all     = _make_action_btn("全选", compact=True)
        b_none    = _make_action_btn("全不选", compact=True)
        b_refresh = _make_action_btn("刷新预览", compact=True)
        b_all.clicked.connect(self._preview_check_all)
        b_none.clicked.connect(self._preview_check_none)
        b_refresh.clicked.connect(self._refresh_preview_table)
        for button in (b_all, b_none, b_refresh):
            h.addWidget(button, 1)
        side.addWidget(self._preview_actions)

        self._preview_table = QTableWidget(0, 7)
        self._preview_table.setHorizontalHeaderLabels(
            ["分区", "名称", "数据类型", "地址/值", "注释", "机架位置", "使用"]
        )
        self._preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview_table.setAlternatingRowColors(True)
        self._preview_table.itemDoubleClicked.connect(self._on_preview_item_double_clicked)
        self._preview_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root.addWidget(self._preview_sidebar, 0)
        root.addWidget(self._preview_table, 1)
        return w

    def _on_preview_item_changed(self, _item: QListWidgetItem) -> None:
        if self._building_tabs:
            return
        self._schedule_preview_refresh(immediate=True)

    def _preview_check_all(self) -> None:
        if not self._preview_list:
            return
        self._preview_list.blockSignals(True)
        for i in range(self._preview_list.count()):
            self._preview_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._preview_list.blockSignals(False)
        self._schedule_preview_refresh(immediate=True)

    def _preview_check_none(self) -> None:
        if not self._preview_list:
            return
        self._preview_list.blockSignals(True)
        for i in range(self._preview_list.count()):
            self._preview_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._preview_list.blockSignals(False)
        self._schedule_preview_refresh(immediate=True)

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

    # ── 通道编辑器（含分区信息侧边栏） ────────────────────────────────────

    def _make_channel_editor(self, zone_id: str = "") -> tuple[QWidget, IoTableWidget]:
        outer = QWidget()
        outer_h = QHBoxLayout(outer)
        outer_h.setContentsMargins(8, 8, 8, 8)
        outer_h.setSpacing(12)

        table = IoTableWidget()
        table.setItemDelegateForColumn(COL_DTYPE, DataTypeDelegate(table))
        table.setItemDelegateForColumn(COL_NAME, NameCompleterDelegate(table, table))
        table.setItemDelegateForColumn(COL_COMMENT, NameCompleterDelegate(table, table, source_column=COL_COMMENT))
        table.contentDirty.connect(lambda reason, current=table: self._on_channel_table_dirty(current, reason))
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer_h.addWidget(table, 1)

        # 中间按钮面板
        btn_col = QWidget()
        btn_col.setFixedWidth(170)
        bv = QVBoxLayout(btn_col)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(8)

        btn_add   = _make_action_btn("添加行",   "在末尾追加空行", icon_name="add-light")
        btn_del   = _make_action_btn("删除选中", "删除选中行", danger=True, icon_name="trash-light")
        btn_add.setMinimumHeight(36)
        btn_del.setMinimumHeight(36)
        bv.addWidget(btn_add)
        bv.addWidget(btn_del)
        bv.addSpacing(10)

        shortcuts = QLabel(
            "<b>快捷键速查</b><br>"
            "Ctrl+D　向下填充<br>"
            "Ctrl+C/V　复制/粘贴<br>"
            "Delete　清除单元格<br>"
            "Tab　移动到下一列<br>"
            "Enter　移动到下一行<br>"
            "Ctrl+Z/Y　撤销/重做<br>"
            "<br>"
            "<b>名称补全</b><br>"
            "在表格聚焦时生效<br>"
            "方向键选择建议，Enter 确认"
        )
        shortcuts.setWordWrap(True)
        shortcuts.setStyleSheet(
            "font-size: 8pt; color: #6070A0; "
            "background: #EEF2FF; border-radius: 6px; "
            "padding: 8px;"
        )
        bv.addWidget(shortcuts)
        bv.addStretch()

        outer_h.addWidget(btn_col, 0)

        # 右侧分区信息面板
        zone_panel = ZoneInfoPanel()
        zone_panel.set_zone_by_id(zone_id)
        outer_h.addWidget(zone_panel, 0)

        btn_add.clicked.connect(lambda: self._add_row_to(table))
        btn_del.clicked.connect(lambda: self._del_rows_in(table))

        return outer, table

    # ── Tab 管理 ──────────────────────────────────────────────────────────

    def _rebuild_tabs(self, select_index: int = 0) -> None:
        self._building_tabs = True
        self._flush_all_channel_tables()
        assert self._tabs is not None
        while self._tabs.count():
            self._tabs.removeTab(0)
        self._channel_tables.clear()

        self._tabs.addTab(self._build_preview_tab(), PREVIEW_LABEL)

        for ch in self._project.channels:
            w, tbl = self._make_channel_editor(ch.zone_id)
            self._channel_tables.append(tbl)
            self._load_table_from_points(tbl, ch.points)
            tab_idx = self._tabs.addTab(w, ch.name)
            self._color_tab(tab_idx, ch.zone_id)

        self._sync_preview_channel_list()
        self._building_tabs = False
        self._preview_dirty = True
        self._prev_tab_index = None
        idx = max(0, min(select_index, self._tabs.count() - 1))
        self._tabs.setCurrentIndex(idx)
        self._prev_tab_index = idx
        if idx == 0:
            self._ensure_preview_fresh()

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

    def _del_rows_in(self, table: IoTableWidget) -> None:
        table._delete_selected_rows()

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
        if self._building_tabs:
            return
        self._sync_table_to_project(table)
        self._set_modified(True)
        self._schedule_preview_refresh()

    def _flush_all_channel_tables(self) -> None:
        for i, tbl in enumerate(self._channel_tables):
            if i < len(self._project.channels):
                self._project.channels[i].points = self._read_points_from_table(tbl)

    def _on_tab_changed(self, idx: int) -> None:
        if self._building_tabs or self._tabs is None:
            return
        self._prev_tab_index = idx
        if idx == 0:
            self._sync_preview_channel_list()
            self._ensure_preview_fresh()

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
            added_any = True

        if not added_any:
            return

        self._sync_preview_channel_list()
        self._schedule_preview_refresh()
        self._tabs.setCurrentIndex(self._tabs.count() - 1)
        self._set_modified(True)

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

    # ══════════════════════════════════════════════════════════════════════════
    # 工具栏 & 菜单
    # ══════════════════════════════════════════════════════════════════════════

    def _build_menu_toolbar(self) -> None:
        self._title_bar = AppTitleBar(self)
        self.setMenuWidget(self._title_bar)

        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)

        def _make_action(
            label: str,
            slot,
            shortcut=None,
            tip: str = "",
            icon_name: str = "",
        ) -> QAction:  # noqa: ANN001
            action = QAction(label, self)
            action.triggered.connect(slot)
            if shortcut:
                action.setShortcut(shortcut)
            if tip:
                action.setToolTip(tip)
                action.setStatusTip(tip)
            if icon_name:
                action.setIcon(load_icon(icon_name))
            return action

        actions = {
            "new": _make_action("新建", self._new_project, QKeySequence.StandardKey.New, "新建项目（重置为 8 个标准分区）", "new"),
            "open": _make_action("打开 JSON…", self._open_json, QKeySequence.StandardKey.Open, "打开已有 JSON 项目文件", "open"),
            "save": _make_action("保存 JSON", self._save_json, QKeySequence.StandardKey.Save, "保存当前项目", "save"),
            "save_as": _make_action(
                "另存为…",
                self._save_json_as,
                QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_S),
                "另存为新文件",
                "save",
            ),
            "import_excel": _make_action("导入 Excel…", self._import_excel, tip="从 Excel 文件导入 IO 表", icon_name="import"),
            "import_first": _make_action("导入首个工作表", self._import_excel_first_sheet, icon_name="import"),
            "export_excel": _make_action("导出 Excel…", self._export_excel, icon_name="export"),
            "export_csv": _make_action("导出 CSV…", self._export_csv_io, icon_name="export"),
            "quit": _make_action("退出", self.close, QKeySequence.StandardKey.Quit),
            "preferences": _make_action("偏好设置…", self._open_preferences),
        }

        for key in ("new", "open", "save", "save_as"):
            tb.addAction(actions[key])
        tb.addSeparator()
        for key in ("import_excel", "import_first", "export_excel", "export_csv"):
            tb.addAction(actions[key])
        toolbar_icons = {
            "new": "new-light",
            "open": "open-light",
            "save": "save-light",
            "save_as": "save-light",
            "import_excel": "import-light",
            "import_first": "import-light",
            "export_excel": "export-light",
            "export_csv": "export-light",
        }
        for key, icon_name in toolbar_icons.items():
            button = tb.widgetForAction(actions[key])
            if button is not None:
                button.setIcon(load_icon(icon_name))

        # ── 菜单栏：文件 ──────────────────────────────────────────────────
        file_menu = QMenu("文件", self)
        edit_menu = QMenu("编辑", self)
        self._title_bar.add_menu("文件", file_menu)
        self._title_bar.add_menu("编辑", edit_menu)

        file_menu.addAction(actions["new"])
        file_menu.addAction(actions["open"])
        file_menu.addAction(actions["save"])
        file_menu.addAction(actions["save_as"])
        file_menu.addSeparator()

        # 最近文件子菜单
        self._recent_menu = QMenu("最近文件(&R)", file_menu)
        file_menu.addMenu(self._recent_menu)
        self._rebuild_recent_menu()

        file_menu.addSeparator()
        file_menu.addAction(actions["quit"])

        # ── 菜单栏：编辑 ──────────────────────────────────────────────────
        edit_menu.addAction(actions["preferences"])

    def _rebuild_recent_menu(self) -> None:
        """重建"最近文件"子菜单。"""
        self._recent_menu.clear()
        recents = get_prefs().recent_files()
        if not recents:
            act = self._recent_menu.addAction("（无最近文件）")
            act.setEnabled(False)
        else:
            for i, p in enumerate(recents):
                label = f"&{i+1}  {Path(p).name}  —  {p}" if i < 9 else f"   {Path(p).name}  —  {p}"
                act = self._recent_menu.addAction(label)
                # 捕获变量
                act.triggered.connect(lambda checked=False, path=p: self._open_recent(path))
            self._recent_menu.addSeparator()
            self._recent_menu.addAction("清空最近文件", self._clear_recent)
        self._rebuild_recent_projects_list()

    def _rebuild_recent_projects_list(self) -> None:
        if self._recent_projects_list is None:
            return
        prefs = get_prefs()
        recents = prefs.recent_files()
        self._recent_projects_list.clear()
        show_full_path = prefs.show_recent_full_path() if hasattr(prefs, "show_recent_full_path") else False
        for path in recents:
            file_path = Path(path)
            if file_path.exists():
                modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(file_path.stat().st_mtime))
                display_path = str(file_path.resolve()) if show_full_path else str(file_path.parent)
                detail = f"{display_path}\n最近修改：{modified}"
            else:
                display_path = str(file_path.resolve()) if show_full_path else str(file_path.parent)
                detail = f"{display_path}\n文件不存在"
            item = QListWidgetItem(f"{file_path.name}\n{detail}")
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(QSize(0, 54))
            if self._project_path and Path(path) == self._project_path:
                item.setBackground(QColor("#E8EFFD"))
                item.setForeground(QColor("#1E4FA3"))
            elif not file_path.exists():
                item.setForeground(QColor("#9A5A5A"))
            self._recent_projects_list.addItem(item)
        self._filter_recent_projects_list(self._recent_filter_edit.text() if self._recent_filter_edit else "")
        self._refresh_recent_project_actions()

    def _on_recent_project_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str) and path:
            self._open_recent(path)

    def _filter_recent_projects_list(self, text: str) -> None:
        if self._recent_projects_list is None:
            return
        query = text.strip().casefold()
        for index in range(self._recent_projects_list.count()):
            item = self._recent_projects_list.item(index)
            haystack = f"{item.text()} {item.toolTip()}".casefold()
            item.setHidden(bool(query) and query not in haystack)

    def _selected_recent_project_path(self) -> str | None:
        if self._recent_projects_list is None:
            return None
        item = self._recent_projects_list.currentItem()
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        return path if isinstance(path, str) else None

    def _refresh_recent_project_actions(self) -> None:
        has_current = self._selected_recent_project_path() is not None
        if self._recent_open_btn is not None:
            self._recent_open_btn.setEnabled(has_current)
        if self._recent_remove_btn is not None:
            self._recent_remove_btn.setEnabled(has_current)

    def _open_selected_recent_project(self) -> None:
        path = self._selected_recent_project_path()
        if path:
            self._open_recent(path)

    def _remove_selected_recent_project(self) -> None:
        path = self._selected_recent_project_path()
        if not path:
            return
        get_prefs().remove_recent(path)
        self._rebuild_recent_menu()

    def _clean_recent_projects(self) -> None:
        prefs = get_prefs()
        removed_any = False
        for path in list(prefs.recent_files()):
            if not Path(path).exists():
                prefs.remove_recent(path)
                removed_any = True
        if removed_any:
            self._rebuild_recent_menu()
        self.statusBar().showMessage("最近项目已清理", 2500)

    def _open_recent(self, path: str) -> None:
        if not Path(path).exists():
            self._dialog_warning("最近文件", f"文件不存在：\n{path}")
            get_prefs().remove_recent(path)
            self._rebuild_recent_menu()
            return
        self._do_open_json(path)

    def _clear_recent(self) -> None:
        get_prefs().clear_recent()
        self._rebuild_recent_menu()

    def _open_preferences(self) -> None:
        prefs = get_prefs()
        dialog = PreferencesDialog(
            autosave_enabled=prefs.autosave_enabled(),
            autosave_interval=prefs.autosave_interval(),
            recent_limit=prefs.recent_limit(),
            show_recent_full_path=prefs.show_recent_full_path(),
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        prefs.set_autosave_enabled(bool(values["autosave_enabled"]))
        prefs.set_autosave_interval(int(values["autosave_interval"]))
        prefs.set_recent_limit(int(values["recent_limit"]))
        prefs.set_show_recent_full_path(bool(values["show_recent_full_path"]))
        self._reset_autosave_timer()
        self._rebuild_recent_menu()
        self.statusBar().showMessage("偏好设置已更新", 3000)
        self._show_toast("偏好设置", "软件偏好已保存", "success")

    def _autosave_settings(self) -> None:
        self._open_preferences()

    # ══════════════════════════════════════════════════════════════════════════
    # 元数据
    # ══════════════════════════════════════════════════════════════════════════

    def _on_meta_changed(self) -> None:
        self._project.name       = self._name_edit.text().strip() or "未命名"
        self._project.plc_prefix = self._plc_edit.text().strip() or "PLC"
        self._set_modified(True)
        self._update_title()

    def _sync_meta_from_project(self) -> None:
        self._name_edit.blockSignals(True)
        self._name_edit.setText(self._project.name)
        self._name_edit.blockSignals(False)
        self._plc_edit.blockSignals(True)
        self._plc_edit.setText(self._project.plc_prefix)
        self._plc_edit.blockSignals(False)

    # ══════════════════════════════════════════════════════════════════════════
    # 复制 / 导出
    # ══════════════════════════════════════════════════════════════════════════

    def _copy_io(self) -> None:
        assert self._tabs is not None
        if self._tabs.currentIndex() == 0:
            self._ensure_preview_fresh()
            rows = rows_io_preview_stitched(self._project, self._selected_preview_channel_order())
        else:
            rows = rows_io_table_channel(self._project, self._tabs.currentIndex() - 1)
        self._copy_tsv(rows)

    def _copy_symbol(self) -> None:
        assert self._tabs is not None
        if self._tabs.currentIndex() == 0:
            self._ensure_preview_fresh()
            pts = stitched_points(self._project, self._selected_preview_channel_order())
        else:
            ci = self._tabs.currentIndex() - 1
            pts = list(self._project.channels[ci].points)
        self._copy_tsv(rows_symbol_table_for_points(self._project, pts))

    def _copy_d(self) -> None:
        assert self._tabs is not None
        if self._tabs.currentIndex() == 0:
            self._ensure_preview_fresh()
            pts = stitched_points(self._project, self._selected_preview_channel_order())
        else:
            ci = self._tabs.currentIndex() - 1
            pts = list(self._project.channels[ci].points)
        self._copy_tsv(rows_d_channel_for_points(self._project, pts))

    def _copy_cio(self) -> None:
        assert self._tabs is not None
        if self._tabs.currentIndex() == 0:
            self._ensure_preview_fresh()
            pts = stitched_points(self._project, self._selected_preview_channel_order())
        else:
            ci = self._tabs.currentIndex() - 1
            pts = list(self._project.channels[ci].points)
        self._copy_tsv(rows_cio_word_index_for_points(self._project, pts))

    def _copy_tsv(self, rows) -> None:
        text = tsv_from_rows(rows)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("✔ 已复制 TSV 到剪贴板", 3000)

    def _copy_combined(self) -> None:
        QApplication.clipboard().setText(combined_export_text(self._project))
        self.statusBar().showMessage("✔ 已复制合并文本（全部分区）到剪贴板", 3000)

    # ══════════════════════════════════════════════════════════════════════════
    # 文件操作
    # ══════════════════════════════════════════════════════════════════════════

    def _confirm_discard(self) -> bool:
        """若有未保存修改，询问用户是否放弃。返回 True 表示可继续操作。"""
        if not self._modified:
            return True
        ret = self._dialog_message(
            "未保存的修改",
            "当前项目有未保存的修改，是否保存？",
            buttons=("保存", "不保存", "取消"),
        )
        if ret == "保存":
            self._save_json()
            return not self._modified  # 若保存成功 _modified 会被置 False
        elif ret == "不保存":
            return True
        return False  # Cancel

    def _new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._project      = IoProject(name="新项目")
        self._project_path = None
        # 清空表格引用，防止旧表格数据覆盖新项目
        self._channel_tables.clear()
        self._set_modified(False)
        self._sync_meta_from_project()
        self._rebuild_tabs(select_index=1)
        self._update_title()

    def _open_json(self) -> None:
        if not self._confirm_discard():
            return
        prefs = get_prefs()
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", prefs.last_dir(), "JSON (*.json)"
        )
        if not path:
            return
        self._do_open_json(path)

    def _do_open_json(self, path: str) -> None:
        try:
            self._project      = load_project_json(path)
            self._project_path = Path(path)
        except Exception as e:
            self._dialog_error("错误", str(e))
            return
        # 清空表格引用，防止旧表格数据覆盖新加载的项目
        self._channel_tables.clear()
        prefs = get_prefs()
        prefs.add_recent(path)
        prefs.set_last_dir(path)
        self._rebuild_recent_menu()
        self._sync_meta_from_project()
        self._rebuild_tabs(select_index=1)
        self._set_modified(False)
        self._update_title()
        self.statusBar().showMessage(f"✔ 已打开 {path}", 3000)

    def _save_json(self) -> None:
        path = str(self._project_path) if self._project_path else ""
        if not path:
            self._save_json_as()
            return
        self._do_save_json(path)

    def _save_json_as(self) -> None:
        prefs = get_prefs()
        path, _ = QFileDialog.getSaveFileName(
            self, "保存项目", prefs.last_dir(), "JSON (*.json)"
        )
        if not path:
            return
        self._do_save_json(path)

    def _do_save_json(self, path: str) -> None:
        self._on_meta_changed()
        self._flush_all_channel_tables()
        try:
            save_project_json(self._project, path)
            self._project_path = Path(path)
            prefs = get_prefs()
            prefs.add_recent(path)
            prefs.set_last_dir(path)
            self._rebuild_recent_menu()
            self._set_modified(False)
            self._update_title()
            clear_autosave()  # 成功保存后清除自动保存槽
            self.statusBar().showMessage(f"✔ 已保存 {path}", 3000)
            self._show_toast("保存成功", f"项目已保存到 {Path(path).name}", "success")
        except Exception as e:
            self._show_toast("保存失败", str(e), "error")
            self._dialog_error("保存失败", str(e))

    def _import_excel(self) -> None:
        prefs = get_prefs()
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Excel", prefs.last_dir(), "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            proj = import_io_sheet(path, sheet_name="IO表")
        except ValueError:
            try:
                proj = import_flat_table(path, sheet_index=0)
            except Exception as e:
                self._dialog_error("导入失败", str(e)); return
        except Exception as e:
            self._dialog_error("导入失败", str(e)); return
        self._project = proj
        self._project_path = None
        # 清空表格引用，防止旧表格数据覆盖新项目
        self._channel_tables.clear()
        prefs.set_last_dir(path)
        self._sync_meta_from_project()
        self._rebuild_tabs(select_index=1)
        self._set_modified(True)
        n = sum(len(c.points) for c in self._project.channels)
        self.statusBar().showMessage(f"✔ 已导入 {n} 点", 3000)

    def _import_excel_first_sheet(self) -> None:
        prefs = get_prefs()
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Excel", prefs.last_dir(), "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            self._project = import_flat_table(path, sheet_index=0)
        except Exception as e:
            self._dialog_error("导入失败", str(e)); return
        self._project_path = None
        # 清空表格引用，防止旧表格数据覆盖新项目
        self._channel_tables.clear()
        prefs.set_last_dir(path)
        self._sync_meta_from_project()
        self._rebuild_tabs(select_index=1)
        self._set_modified(True)
        n = sum(len(c.points) for c in self._project.channels)
        self.statusBar().showMessage(f"✔ 已导入 {n} 点", 3000)

    def _export_excel(self) -> None:
        self._flush_all_channel_tables()
        prefs = get_prefs()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Excel", prefs.last_dir(), "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            save_project_excel(self._project, path)
            prefs.set_last_dir(path)
            self.statusBar().showMessage(f"✔ 已导出 {path}", 3000)
        except Exception as e:
            self._dialog_error("导出失败", str(e))

    def _export_csv_io(self) -> None:
        self._flush_all_channel_tables()
        prefs = get_prefs()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", prefs.last_dir(), "CSV (*.csv)"
        )
        if not path:
            return
        text = csv_from_rows(rows_io_table(self._project))
        try:
            Path(path).write_text(text, encoding="utf-8-sig")
            prefs.set_last_dir(path)
            self.statusBar().showMessage(f"✔ 已导出 {path}", 3000)
        except Exception as e:
            self._dialog_error("导出失败", str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # 关闭事件
    # ══════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event) -> None:  # noqa: ANN001
        if self._modified:
            if not self._confirm_discard():
                event.ignore()
                return
        self._autosave_timer.stop()
        self._autosave_recovery_timer.stop()
        clear_autosave()
        event.accept()
