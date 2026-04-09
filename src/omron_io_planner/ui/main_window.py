# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
import json
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QShortcut
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
    QToolButton,
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
from ..auto_name import normalize_project_auto_names
from ..io_excel import import_flat_table, import_io_sheet, save_project_excel
from ..models import IoChannel, IoPoint, IoProject
from ..omron_symbol_types import combo_items
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
    FindReplaceDialog,
    IntInputDialog,
    LoadingPopup,
    BatchGenerateDialog,
    BulkRowUpdateDialog,
    MessageDialog,
    PreferencesDialog,
    ProjectSettingsDialog,
    TextInputDialog,
    ToastPopup,
)
from .icons import load_icon
from .io_table_widget import IoTableWidget, _next_omron_bit, _render_generation_template
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

PREVIEW_LABEL = "全通道预览"
LEGACY_PREVIEW_LABEL = "📊 全通道预览"
_PREVIEW_TABLE_HEADERS = ["分区", "名称", "数据类型", "地址/值", "注释", "机架位置", "使用"]
_PREVIEW_COLUMN_WIDTH_LIMITS = {
    0: (84, 140),
    1: (120, 320),
    2: (96, 140),
    3: (96, 150),
    4: (120, 420),
    5: (96, 220),
    6: (96, 260),
}

_APP_TITLE = "欧姆龙 IO 分配助手"
_VALID_DATA_TYPES = set(combo_items())
_FALLBACK_EDITOR_DEFAULTS = {
    "continuous_entry": True,
    "enter_navigation": "down",
    "tab_navigation": "right",
    "auto_increment_address": True,
    "inherit_data_type": True,
    "inherit_rack": True,
    "inherit_usage": True,
    "auto_increment_name": True,
    "auto_increment_comment": True,
    "suggestions_enabled": True,
    "suggestion_limit": 8,
    "default_immersive": False,
    "row_height": 34,
    "default_column_layout": {},
    "name_phrases": [],
    "comment_phrases": [],
    "generation_defaults": {
        "start_address": "",
        "row_count": 8,
        "data_type": "BOOL",
        "name_template": "",
        "comment_template": "",
        "rack": "",
        "usage": "",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _next_address_value(address: str) -> str:
    nxt = _next_omron_bit(address)
    return nxt if nxt else address


def _is_preview_tab_label(label: str) -> bool:
    return label in {PREVIEW_LABEL, LEGACY_PREVIEW_LABEL}


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
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return btn


def _make_immersive_btn(
    text: str,
    *,
    tooltip: str = "",
    danger: bool = False,
    icon_name: str = "",
) -> QPushButton:
    btn = _make_action_btn(text, tooltip=tooltip, danger=danger, compact=True, icon_name=icon_name)
    btn.setMinimumWidth(max(82, btn.sizeHint().width()))
    btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return btn


class _RecentProjectItemWidget(QWidget):
    """最近项目条目，右侧带快捷操作按钮。"""

    open_requested = Signal(str)
    pin_requested = Signal(str, bool)
    remove_requested = Signal(str)

    def __init__(
        self,
        entry: dict[str, object],
        show_full_path: bool,
        *,
        active: bool = False,
        missing: bool = False,
        open_callback=None,
        pin_callback=None,
        remove_callback=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("recentProjectItemWidget")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._path = str(entry.get("path", "") or "")
        self._pinned = bool(entry.get("pinned", False))
        self._open_callback = open_callback
        self._pin_callback = pin_callback
        self._remove_callback = remove_callback
        self.setProperty("activeProject", active)
        self.setProperty("missingProject", missing)
        self.setProperty("pinnedProject", self._pinned)

        path = Path(self._path)
        self._title_text = path.name or self._path
        self._path_text = str(path.resolve()) if show_full_path else str(path.parent)
        self._meta_text = self._build_meta_text(entry, active=active, missing=missing)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 8, 8)
        root.setSpacing(8)

        self._text_box = QWidget(self)
        self._text_box.setObjectName("recentProjectItemTextBox")
        self._text_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        text_layout = QVBoxLayout(self._text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self._title_label = QLabel("", self._text_box)
        self._title_label.setObjectName("recentProjectItemTitle")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._path_label = QLabel("", self._text_box)
        self._path_label.setObjectName("recentProjectItemPath")
        self._path_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._meta_label = QLabel("", self._text_box)
        self._meta_label.setObjectName("recentProjectItemMeta")
        self._meta_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_layout.addWidget(self._title_label)
        text_layout.addWidget(self._path_label)
        text_layout.addWidget(self._meta_label)
        self._meta_label.hide()

        root.addWidget(self._text_box, 1)

        button_box = QWidget(self)
        button_box.setObjectName("recentProjectItemActionsBox")
        button_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        button_layout = QVBoxLayout(button_box)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        self._pin_btn = self._make_action_button("recentProjectActionButton", "置顶", load_icon("pin"))
        self._pin_btn.setCheckable(True)
        self._pin_btn.setChecked(self._pinned)
        self._remove_btn = self._make_action_button(
            "recentProjectActionButton",
            "移除最近项目",
            load_icon("trash"),
            danger=True,
        )

        self._pin_btn.toggled.connect(self._on_pin_toggled)
        self._remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._path))
        if self._open_callback is not None:
            self.open_requested.connect(self._open_callback)
        if self._pin_callback is not None:
            self.pin_requested.connect(self._pin_callback)
        if self._remove_callback is not None:
            self.remove_requested.connect(self._remove_callback)
        for button in (self._pin_btn, self._remove_btn):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(14, 14))
            button.setFixedSize(24, 24)
            button_layout.addWidget(button)
        button_layout.addStretch(1)

        root.addWidget(button_box, 0)
        self.setMinimumHeight(70)
        self._sync_pin_button()
        QTimer.singleShot(0, self._refresh_text_elision)

    def _build_meta_text(self, entry: dict[str, object], *, active: bool, missing: bool) -> str:
        tokens: list[str] = []
        if active:
            tokens.append("当前项目")
        if self._pinned:
            tokens.append("已置顶")
        if missing:
            tokens.append("文件不存在")
        else:
            saved_at = float(entry.get("last_saved", 0.0) or 0.0)
            opened_at = float(entry.get("last_opened", 0.0) or 0.0)
            stamp = saved_at or opened_at
            if stamp > 0:
                label = "最近保存" if saved_at >= opened_at else "最近打开"
                tokens.append(f"{label} {time.strftime('%m-%d %H:%M', time.localtime(stamp))}")
            elif not tokens:
                tokens.append("可直接打开")
        return " · ".join(tokens)

    def _make_action_button(self, object_name: str, tooltip: str, icon, danger: bool = False) -> QToolButton:  # noqa: ANN001
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setToolTip(tooltip)
        button.setIcon(icon)
        button.setAutoRaise(True)
        if danger:
            button.setProperty("danger", "true")
        return button

    def _sync_pin_button(self) -> None:
        if self._pin_btn.isChecked():
            self._pin_btn.setIcon(load_icon("pin-light"))
            self._pin_btn.setToolTip("取消置顶")
            self._pin_btn.setProperty("pinned", "true")
        else:
            self._pin_btn.setIcon(load_icon("pin"))
            self._pin_btn.setToolTip("置顶")
            self._pin_btn.setProperty("pinned", "false")
        self.setProperty("pinnedProject", self._pin_btn.isChecked())
        self.style().unpolish(self)
        self.style().polish(self)
        self._pin_btn.style().unpolish(self._pin_btn)
        self._pin_btn.style().polish(self._pin_btn)

    def _refresh_text_elision(self) -> None:
        available = max(120, self._text_box.width() - 4)
        self._title_label.setText(
            self._title_label.fontMetrics().elidedText(
                self._title_text,
                Qt.TextElideMode.ElideRight,
                available,
            )
        )
        self._path_label.setText(
            self._path_label.fontMetrics().elidedText(
                self._path_text,
                Qt.TextElideMode.ElideMiddle,
                available,
            )
        )
        if self._meta_text:
            self._meta_label.setText(
                self._meta_label.fontMetrics().elidedText(
                    self._meta_text,
                    Qt.TextElideMode.ElideRight,
                    available,
                )
            )
            self._meta_label.show()
        else:
            self._meta_label.clear()
            self._meta_label.hide()

    def _on_pin_toggled(self, checked: bool) -> None:
        self._sync_pin_button()
        self.pin_requested.emit(self._path, checked)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        self._refresh_text_elision()
        super().resizeEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 94 if self._meta_text else 84)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint()) if hasattr(event, "position") else self.childAt(event.pos())
            if child not in (self._pin_btn, self._remove_btn):
                self.open_requested.emit(self._path)
        super().mouseReleaseEvent(event)


class _ClickableHeader(QWidget):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._title_bar: AppTitleBar | None = None
        self._toolbar: QToolBar | None = None
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
        self._sidebar: QWidget | None = None
        self._recent_group: QGroupBox | None = None
        self._recent_projects_list: QListWidget | None = None
        self._recent_filter_edit: QLineEdit | None = None
        self._recent_clean_btn: QToolButton | None = None
        self._recent_click_pending_activation: str | None = None
        self._project_meta_group: QGroupBox | None = None
        self._copy_group: QGroupBox | None = None
        self._validation_group: QGroupBox | None = None
        self._validation_header: QWidget | None = None
        self._validation_body: QWidget | None = None
        self._validation_toggle_btn: QPushButton | None = None
        self._validation_summary_label: QLabel | None = None
        self._validation_list: QListWidget | None = None
        self._validation_issues: list[dict[str, object]] = []
        self._validation_collapsed = True
        self._tabs: QTabWidget | None = None
        self._modified = False          # 未保存修改标记
        self._toast: ToastPopup | None = None
        self._loading_popup: LoadingPopup | None = None
        self._immersive_mode = False
        self._immersive_action: QAction | None = None
        self._btn_enter_immersive: QPushButton | None = None
        self._editor_focus_bars: dict[IoTableWidget, QWidget] = {}
        self._editor_side_panels: dict[IoTableWidget, QWidget] = {}
        self._editor_filter_edits: dict[IoTableWidget, QLineEdit] = {}
        self._editor_filled_toggles: dict[IoTableWidget, QPushButton] = {}
        self._find_replace_dialog: FindReplaceDialog | None = None
        self._find_replace_context: dict[str, object] = {
            "table": None,
            "query": "",
            "case_sensitive": False,
            "direction": "forward",
            "current_column_only": False,
            "selected_only": False,
            "base_column": None,
            "match": None,
        }
        self._batch_help_labels: dict[IoTableWidget, QLabel] = {}
        self._resize_margin = 8
        self._resize_watch_ids: set[int] = set()
        self._opening_recent_path: str | None = None
        self._opening_recent_started_at = 0.0
        self._restoring_workspace = False

        self.setWindowTitle(_APP_TITLE)
        self.resize(1786, 930)
        self.setStyleSheet(app_stylesheet())

        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(150)
        self._preview_refresh_timer.timeout.connect(self._refresh_preview_table)

        self._validation_refresh_timer = QTimer(self)
        self._validation_refresh_timer.setSingleShot(True)
        self._validation_refresh_timer.setInterval(120)
        self._validation_refresh_timer.timeout.connect(self._refresh_validation_panel)

        self._autosave_recovery_timer = QTimer(self)
        self._autosave_recovery_timer.setSingleShot(True)
        self._autosave_recovery_timer.setInterval(200)
        self._autosave_recovery_timer.timeout.connect(self._check_autosave_recovery)

        self._build_ui()
        self._build_menu_toolbar()
        self._rebuild_tabs(select_index=1)
        startup_prefs = get_prefs().startup_preferences() if hasattr(get_prefs(), "startup_preferences") else {}
        if self._recent_group is not None and not bool(startup_prefs.get("show_recent_sidebar", True)):
            self._recent_group.hide()

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

        self._install_resize_watchers(self)
        if bool(startup_prefs.get("auto_open_recent", False)):
            recent_files = get_prefs().recent_files()
            if recent_files:
                QTimer.singleShot(0, lambda path=recent_files[0]: self._open_recent(path))

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

    def _install_resize_watchers(self, root: QWidget) -> None:
        for widget in [root, *root.findChildren(QWidget)]:
            widget_id = id(widget)
            if widget_id in self._resize_watch_ids:
                continue
            self._resize_watch_ids.add(widget_id)
            widget.installEventFilter(self)
            widget.setMouseTracking(True)

    @contextmanager
    def _suspend_visible_updates(self):
        widgets: list[tuple[QWidget, bool]] = []
        seen_ids: set[int] = set()
        for widget in (self, self.centralWidget(), self._tabs):
            if widget is None:
                continue
            widget_id = id(widget)
            if widget_id in seen_ids:
                continue
            seen_ids.add(widget_id)
            widgets.append((widget, widget.updatesEnabled()))

        for widget, _enabled in widgets:
            widget.setUpdatesEnabled(False)

        try:
            yield
        finally:
            for widget, enabled in reversed(widgets):
                widget.setUpdatesEnabled(enabled)
            for widget, _enabled in widgets:
                widget.update()

    def _resize_edges_for_pos(self, pos: QPoint):
        if self.isMaximized() or self.isFullScreen():
            return None
        width = self.width()
        height = self.height()
        if width <= 0 or height <= 0:
            return None
        margin = self._resize_margin
        edges = None
        if pos.x() <= margin:
            edges = Qt.Edge.LeftEdge
        elif pos.x() >= width - margin:
            edges = Qt.Edge.RightEdge
        if pos.y() <= margin:
            edges = (edges | Qt.Edge.TopEdge) if edges is not None else Qt.Edge.TopEdge
        elif pos.y() >= height - margin:
            edges = (edges | Qt.Edge.BottomEdge) if edges is not None else Qt.Edge.BottomEdge
        return edges

    def _resize_cursor_shape(self, edges) -> Qt.CursorShape | None:
        if edges is None:
            return None
        edge_value = int(getattr(edges, "value", edges))
        diagonal_a = int(getattr(Qt.Edge.LeftEdge | Qt.Edge.TopEdge, "value", Qt.Edge.LeftEdge | Qt.Edge.TopEdge))
        diagonal_b = int(getattr(Qt.Edge.RightEdge | Qt.Edge.BottomEdge, "value", Qt.Edge.RightEdge | Qt.Edge.BottomEdge))
        diagonal_c = int(getattr(Qt.Edge.RightEdge | Qt.Edge.TopEdge, "value", Qt.Edge.RightEdge | Qt.Edge.TopEdge))
        diagonal_d = int(getattr(Qt.Edge.LeftEdge | Qt.Edge.BottomEdge, "value", Qt.Edge.LeftEdge | Qt.Edge.BottomEdge))
        if edge_value in (diagonal_a, diagonal_b):
            return Qt.CursorShape.SizeFDiagCursor
        if edge_value in (diagonal_c, diagonal_d):
            return Qt.CursorShape.SizeBDiagCursor
        if edge_value in (
            int(getattr(Qt.Edge.LeftEdge, "value", Qt.Edge.LeftEdge)),
            int(getattr(Qt.Edge.RightEdge, "value", Qt.Edge.RightEdge)),
        ):
            return Qt.CursorShape.SizeHorCursor
        if edge_value in (
            int(getattr(Qt.Edge.TopEdge, "value", Qt.Edge.TopEdge)),
            int(getattr(Qt.Edge.BottomEdge, "value", Qt.Edge.BottomEdge)),
        ):
            return Qt.CursorShape.SizeVerCursor
        return None

    def eventFilter(self, watched, event) -> bool:  # noqa: ANN001
        if isinstance(watched, QWidget) and (watched is self or self.isAncestorOf(watched)):
            event_type = event.type()
            if event_type in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress) and hasattr(event, "globalPosition"):
                pos = self.mapFromGlobal(event.globalPosition().toPoint())
                edges = self._resize_edges_for_pos(pos)
                cursor_shape = self._resize_cursor_shape(edges)
                if cursor_shape is not None:
                    watched.setCursor(cursor_shape)
                else:
                    watched.unsetCursor()
                if (
                    event_type == QEvent.Type.MouseButtonPress
                    and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton
                    and edges is not None
                ):
                    handle = self.windowHandle()
                    if handle is not None and handle.startSystemResize(edges):
                        return True
            elif event_type == QEvent.Type.Leave:
                watched.unsetCursor()
        return super().eventFilter(watched, event)

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

    def _show_loading_popup(self, title: str, text: str) -> None:
        if self._loading_popup is None:
            self._loading_popup = LoadingPopup(self)
        self._loading_popup.show_message(title, text)
        QApplication.processEvents()

    def _hide_loading_popup(self) -> None:
        if self._loading_popup is not None:
            self._loading_popup.hide()

    def _global_editor_defaults(self) -> dict[str, object]:
        prefs = get_prefs()
        if hasattr(prefs, "editor_defaults"):
            return dict(prefs.editor_defaults())
        return json.loads(json.dumps(_FALLBACK_EDITOR_DEFAULTS, ensure_ascii=False))

    def _project_editor_preferences(self) -> dict[str, object]:
        return dict(self._project.project_preferences.get("editor", {}) or {})

    def _project_phrase_library(self) -> dict[str, list[str]]:
        phrases = self._project.project_preferences.get("phrases", {}) or {}
        return {
            "name": list(phrases.get("name", []) or []),
            "comment": list(phrases.get("comment", []) or []),
        }

    def _effective_editor_defaults(self) -> dict[str, object]:
        return _deep_merge(self._global_editor_defaults(), self._project_editor_preferences())

    def _project_generation_defaults(self) -> dict[str, object]:
        global_defaults = dict(self._global_editor_defaults().get("generation_defaults", {}) or {})
        project_defaults = dict(self._project.project_preferences.get("generation_defaults", {}) or {})
        return _deep_merge(global_defaults, project_defaults)

    def _configure_table_from_preferences(self, table: IoTableWidget) -> None:
        defaults = self._effective_editor_defaults()
        table.set_editor_defaults(defaults)
        phrases = self._project_phrase_library()
        global_defaults = self._global_editor_defaults()
        table.set_phrase_library(
            list(global_defaults.get("name_phrases", []) or []) + phrases["name"],
            list(global_defaults.get("comment_phrases", []) or []) + phrases["comment"],
        )

    def _project_view_state(self) -> dict[str, object]:
        return dict(self._project.workspace_state or {})

    def _begin_recent_load_feedback(self, path: str) -> None:
        self.statusBar().showMessage(f"正在加载 {Path(path).name}...", 0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()

    def _end_recent_load_feedback(self) -> None:
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

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
        self._capture_project_workspace_state()
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
                self.statusBar().showMessage("已恢复自动保存的项目", 4000)
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

        sidebar = QWidget(central)
        sidebar.setObjectName("mainSidebar")
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(300)
        self._sidebar = sidebar
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(12)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(sidebar, 0)

        meta = QGroupBox("项目信息")
        meta.setObjectName("projectMetaGroup")
        self._project_meta_group = meta
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
        sidebar_layout.addWidget(meta, 0)

        recent_group = QGroupBox("最近项目")
        self._recent_group = recent_group
        recent_group.setObjectName("recentProjectsGroup")
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(10, 12, 10, 10)
        recent_layout.setSpacing(8)

        recent_hint = QLabel("展示最近打开或保存的项目；单击直接切换，右侧图标可置顶或移除。")
        recent_hint.setWordWrap(True)
        recent_hint.setStyleSheet("color: #5A6080; font-size: 9pt;")
        recent_layout.addWidget(recent_hint)

        recent_filter_row = QWidget(recent_group)
        recent_filter_row.setObjectName("recentProjectsFilterRow")
        recent_filter_layout = QHBoxLayout(recent_filter_row)
        recent_filter_layout.setContentsMargins(0, 0, 0, 0)
        recent_filter_layout.setSpacing(6)

        self._recent_filter_edit = QLineEdit()
        self._recent_filter_edit.setObjectName("recentProjectsFilter")
        self._recent_filter_edit.setClearButtonEnabled(True)
        self._recent_filter_edit.setPlaceholderText("筛选项目名称或路径")
        self._recent_filter_edit.textChanged.connect(self._filter_recent_projects_list)
        recent_filter_layout.addWidget(self._recent_filter_edit, 1)

        self._recent_clean_btn = QToolButton(recent_filter_row)
        self._recent_clean_btn.setObjectName("recentProjectActionButton")
        self._recent_clean_btn.setToolTip("清理失效项目记录")
        self._recent_clean_btn.setIcon(load_icon("trash"))
        self._recent_clean_btn.setIconSize(QSize(16, 16))
        self._recent_clean_btn.setAutoRaise(True)
        self._recent_clean_btn.setFixedSize(28, 28)
        self._recent_clean_btn.clicked.connect(self._clean_recent_projects)
        recent_filter_layout.addWidget(self._recent_clean_btn, 0)
        recent_layout.addWidget(recent_filter_row)

        self._recent_projects_list = QListWidget()
        self._recent_projects_list.setObjectName("recentProjectsList")
        self._recent_projects_list.setSpacing(8)
        self._recent_projects_list.itemActivated.connect(self._on_recent_project_activated)
        self._recent_projects_list.itemClicked.connect(self._on_recent_project_clicked)
        recent_layout.addWidget(self._recent_projects_list, 1)
        sidebar_layout.addWidget(recent_group, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(content, 1)

        copy_group = QWidget(content)
        copy_group.setObjectName("projectMetaCopyPanel")
        self._copy_group = copy_group
        copy_layout = QVBoxLayout(copy_group)
        copy_layout.setContentsMargins(12, 8, 12, 8)
        copy_layout.setSpacing(6)
        copy_title = QLabel("导出 / 复制到剪贴板", copy_group)
        copy_title.setObjectName("projectMetaCopyTitle")
        copy_layout.addWidget(copy_title)
        copy_buttons_row = QWidget(copy_group)
        copy_buttons_row.setObjectName("projectMetaCopyButtons")
        copy_h = QHBoxLayout(copy_buttons_row)
        copy_h.setContentsMargins(0, 0, 0, 0)
        copy_h.setSpacing(8)
        self._btn_copy_io   = _make_action_btn("IO 表",          "复制当前分区的 IO 表（TSV）", compact=True, icon_name="clipboard-light")
        self._btn_copy_sym  = _make_action_btn("符号表",          "复制当前分区的符号表（TSV）", compact=True, icon_name="clipboard-light")
        self._btn_copy_d    = _make_action_btn("D 区 CHANNEL",   "复制 D 区 CHANNEL 行", compact=True, icon_name="clipboard-light")
        self._btn_copy_cio  = _make_action_btn("CIO 字 CHANNEL", "复制 CIO 字 CHANNEL 行", compact=True, icon_name="clipboard-light")
        self._btn_copy_all  = _make_action_btn("合并全部分区",    "合并所有分区文本到剪贴板", compact=True, icon_name="clipboard-light")
        for btn in (self._btn_copy_io, self._btn_copy_sym, self._btn_copy_d, self._btn_copy_cio, self._btn_copy_all):
            copy_h.addWidget(btn, 0)
        copy_h.addStretch(1)
        copy_layout.addWidget(copy_buttons_row)
        layout.addWidget(copy_group, 0)

        # ── Tab 区 ─────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        tb = self._tabs.tabBar()
        tb.tabBarDoubleClicked.connect(self._on_tab_bar_double_clicked)
        tab_corner_actions = QWidget(self._tabs)
        tab_corner_actions.setObjectName("tabCornerActions")
        tab_corner_layout = QHBoxLayout(tab_corner_actions)
        tab_corner_layout.setContentsMargins(0, 0, 0, 0)
        tab_corner_layout.setSpacing(8)
        self._btn_enter_immersive = _make_action_btn(
            "进入沉浸",
            "聚焦当前分区编辑画布",
            compact=True,
            icon_name="focus-light",
        )
        self._btn_add_ch = _make_action_btn(
            "添加分区",
            "从标准欧姆龙分区列表选择，或添加自定义通道",
            compact=True,
            icon_name="add-light",
        )
        self._btn_del_ch = _make_action_btn(
            "删除当前",
            "删除当前选中分区（至少保留一个）",
            danger=True,
            compact=True,
            icon_name="trash-light",
        )
        tab_corner_layout.addWidget(self._btn_enter_immersive, 0)
        tab_corner_layout.addWidget(self._btn_add_ch, 0)
        tab_corner_layout.addWidget(self._btn_del_ch, 0)
        self._tabs.setCornerWidget(tab_corner_actions, Qt.Corner.TopRightCorner)
        layout.addWidget(self._tabs, stretch=1)

        validation_group = QGroupBox("轻量校验")
        self._validation_group = validation_group
        validation_layout = QVBoxLayout(validation_group)
        validation_layout.setContentsMargins(10, 8, 10, 8)
        validation_layout.setSpacing(6)

        validation_header = _ClickableHeader(validation_group)
        validation_header.setObjectName("validationHeader")
        validation_header.setCursor(Qt.CursorShape.PointingHandCursor)
        validation_header.clicked.connect(self._toggle_validation_panel)
        self._validation_header = validation_header
        validation_header_layout = QHBoxLayout(validation_header)
        validation_header_layout.setContentsMargins(0, 0, 0, 0)
        validation_header_layout.setSpacing(8)
        validation_title = QLabel("仅提示核心错误；地址重复按同一分区/通道判断，双击问题可直接定位。")
        validation_title.setWordWrap(True)
        validation_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        validation_header_layout.addWidget(validation_title, 1)
        self._validation_summary_label = QLabel("", validation_header)
        self._validation_summary_label.setObjectName("validationSummaryLabel")
        self._validation_summary_label.setWordWrap(True)
        self._validation_summary_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._validation_summary_label.hide()
        validation_header_layout.addWidget(self._validation_summary_label, 1)
        self._validation_toggle_btn = _make_action_btn("收起详情", compact=True)
        self._validation_toggle_btn.clicked.connect(self._toggle_validation_panel)
        validation_header_layout.addWidget(self._validation_toggle_btn, 0)
        validation_layout.addWidget(validation_header)

        self._validation_body = QWidget(validation_group)
        self._validation_body.setObjectName("validationBody")
        validation_body_layout = QVBoxLayout(self._validation_body)
        validation_body_layout.setContentsMargins(0, 0, 0, 0)
        validation_body_layout.setSpacing(4)
        self._validation_list = QListWidget(self._validation_body)
        self._validation_list.setMaximumHeight(112)
        self._validation_list.itemDoubleClicked.connect(self._jump_to_validation_issue)
        validation_body_layout.addWidget(self._validation_list)
        validation_layout.addWidget(self._validation_body)
        layout.addWidget(validation_group)

        # 连接
        self._btn_enter_immersive.clicked.connect(lambda: self._set_immersive_mode(not self._immersive_mode))
        self._btn_add_ch.clicked.connect(self._add_channel)
        self._btn_del_ch.clicked.connect(self._delete_current_channel)
        self._btn_copy_io.clicked.connect(self._copy_io)
        self._btn_copy_sym.clicked.connect(self._copy_symbol)
        self._btn_copy_d.clicked.connect(self._copy_d)
        self._btn_copy_cio.clicked.connect(self._copy_cio)
        self._btn_copy_all.clicked.connect(self._copy_combined)
        self._name_edit.textChanged.connect(self._on_meta_changed)
        self._plc_edit.textChanged.connect(self._on_meta_changed)
        self._sync_immersive_corner_button()
        self._sync_channel_action_buttons()

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
        # 地址重复只在同一分区/通道命名空间内检查：
        # - 标准分区按 zone_id 隔离
        # - 自定义通道按当前 channel_index 隔离
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
        self._project.workspace_state = state

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

    def _apply_project_workspace_state(self, fallback_index: int = 1) -> int:
        state = self._project_view_state()
        self._restoring_workspace = True
        try:
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

    def _set_immersive_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self._immersive_mode = enabled
        if self._immersive_action is not None and self._immersive_action.isChecked() != enabled:
            self._immersive_action.blockSignals(True)
            self._immersive_action.setChecked(enabled)
            self._immersive_action.blockSignals(False)
        self._sync_immersive_corner_button()
        startup_prefs = get_prefs().startup_preferences() if hasattr(get_prefs(), "startup_preferences") else {}
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

    # ══════════════════════════════════════════════════════════════════════════
    # 工具栏 & 菜单
    # ══════════════════════════════════════════════════════════════════════════

    def _build_menu_toolbar(self) -> None:
        self._title_bar = AppTitleBar(self)
        self.setMenuWidget(self._title_bar)

        tb = QToolBar("主工具栏")
        self._toolbar = tb
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
            checkable: bool = False,
        ) -> QAction:  # noqa: ANN001
            action = QAction(label, self)
            action.triggered.connect(slot)
            if shortcut:
                action.setShortcut(shortcut)
            action.setCheckable(checkable)
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
            "project_settings": _make_action("项目设置…", self._open_project_settings),
            "reset_project_view": _make_action("重置当前项目视图", self._reset_current_project_view),
            "find": _make_action("查找…", self._open_find_dialog, QKeySequence.StandardKey.Find),
            "replace": _make_action("替换…", self._open_replace_dialog, QKeySequence.StandardKey.Replace),
            "focus_filter": _make_action(
                "聚焦分区筛选框",
                self._focus_current_editor_filter,
                QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_F),
            ),
            "immersive": _make_action(
                "沉浸模式",
                self._set_immersive_mode,
                QKeySequence(Qt.Key.Key_F11),
                "聚焦当前分区编辑画布",
                "focus-light",
                checkable=True,
            ),
        }
        self._immersive_action = actions["immersive"]
        for action in actions.values():
            self.addAction(action)

        for key in ("new", "open", "save", "save_as"):
            tb.addAction(actions[key])
        tb.addSeparator()
        for key in ("import_excel", "import_first", "export_excel", "export_csv"):
            tb.addAction(actions[key])
        tb.addSeparator()
        tb.addAction(actions["immersive"])
        toolbar_icons = {
            "new": "new-light",
            "open": "open-light",
            "save": "save-light",
            "save_as": "save-light",
            "import_excel": "import-light",
            "import_first": "import-light",
            "export_excel": "export-light",
            "export_csv": "export-light",
            "immersive": "focus-light",
        }
        for key, icon_name in toolbar_icons.items():
            button = tb.widgetForAction(actions[key])
            if button is not None:
                button.setIcon(load_icon(icon_name))

        # ── 菜单栏：文件 ──────────────────────────────────────────────────
        file_menu = QMenu("文件", self)
        edit_menu = QMenu("编辑", self)
        view_menu = QMenu("视图", self)
        self._title_bar.add_menu("文件", file_menu)
        self._title_bar.add_menu("编辑", edit_menu)
        self._title_bar.add_menu("视图", view_menu)

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
        edit_menu.addAction(actions["project_settings"])
        edit_menu.addAction(actions["reset_project_view"])
        edit_menu.addSeparator()
        edit_menu.addAction(actions["find"])
        edit_menu.addAction(actions["replace"])
        edit_menu.addAction(actions["focus_filter"])

        # ── 菜单栏：视图 ──────────────────────────────────────────────────
        view_menu.addAction(actions["immersive"])

    def _rebuild_recent_menu(self) -> None:
        """重建"最近文件"子菜单。"""
        recent_prefs = get_prefs()
        recent_workspace = (
            recent_prefs.recent_workspace_preferences()
            if hasattr(recent_prefs, "recent_workspace_preferences")
            else {"auto_prune_missing": True}
        )
        if recent_workspace.get("auto_prune_missing", True):
            self._prune_missing_recent_projects()
        self._recent_menu.clear()
        recents = recent_prefs.recent_projects() if hasattr(recent_prefs, "recent_projects") else [
            {"path": path, "pinned": False} for path in recent_prefs.recent_files()
        ]
        if not recents:
            act = self._recent_menu.addAction("（无最近文件）")
            act.setEnabled(False)
        else:
            for i, entry in enumerate(recents):
                p = str(entry["path"])
                pin = "置顶 · " if bool(entry.get("pinned", False)) else ""
                label = f"&{i+1}  {pin}{Path(p).name}  —  {p}" if i < 9 else f"   {pin}{Path(p).name}  —  {p}"
                act = self._recent_menu.addAction(label)
                # 捕获变量
                act.triggered.connect(lambda checked=False, path=p: self._open_recent(path))
            self._recent_menu.addSeparator()
            self._recent_menu.addAction("清空最近文件", self._clear_recent)
        self._rebuild_recent_projects_list()

    def _prune_missing_recent_projects(self) -> bool:
        prefs = get_prefs()
        removed_any = False
        for path in list(prefs.recent_files()):
            if not Path(path).exists():
                prefs.remove_recent(path)
                removed_any = True
        return removed_any

    def _rebuild_recent_projects_list(self) -> None:
        if self._recent_projects_list is None:
            return
        prefs = get_prefs()
        recents = prefs.recent_projects() if hasattr(prefs, "recent_projects") else [
            {"path": path, "pinned": False, "last_opened": 0.0, "last_saved": 0.0}
            for path in prefs.recent_files()
        ]
        self._recent_projects_list.clear()
        self._recent_click_pending_activation = None
        show_full_path = prefs.show_recent_full_path() if hasattr(prefs, "show_recent_full_path") else False
        for entry in recents:
            path = str(entry["path"])
            file_path = Path(path)
            title = f"置顶 · {file_path.name}" if bool(entry.get("pinned", False)) else file_path.name
            display_path = str(file_path.resolve()) if show_full_path else str(file_path.parent)
            detail = display_path if file_path.exists() else f"{display_path}\n文件不存在"
            item = QListWidgetItem()
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setData(Qt.ItemDataRole.UserRole + 1, bool(entry.get("pinned", False)))
            item.setData(Qt.ItemDataRole.UserRole + 2, f"{title}\n{detail}")
            widget = _RecentProjectItemWidget(
                entry,
                show_full_path,
                active=bool(self._project_path and Path(path) == self._project_path),
                missing=not file_path.exists(),
                open_callback=self._open_recent,
                pin_callback=self._set_recent_project_pinned,
                remove_callback=self._remove_recent_project_entry,
                parent=self._recent_projects_list,
            )
            item.setSizeHint(widget.sizeHint())
            self._recent_projects_list.addItem(item)
            self._recent_projects_list.setItemWidget(item, widget)
        self._filter_recent_projects_list(self._recent_filter_edit.text() if self._recent_filter_edit else "")
        self._refresh_recent_project_actions()

    def _on_recent_project_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str) and path:
            self._recent_click_pending_activation = path
            self._open_recent(path)

    def _on_recent_project_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(path, str) or not path:
            return
        if self._recent_click_pending_activation == path:
            self._recent_click_pending_activation = None
            return
        self._recent_click_pending_activation = None
        self._open_recent(path)

    def _filter_recent_projects_list(self, text: str) -> None:
        if self._recent_projects_list is None:
            return
        query = text.strip().casefold()
        for index in range(self._recent_projects_list.count()):
            item = self._recent_projects_list.item(index)
            search_text = item.data(Qt.ItemDataRole.UserRole + 2)
            haystack = f"{search_text or ''} {item.toolTip()}".casefold()
            item.setHidden(bool(query) and query not in haystack)

    def _selected_recent_project_path(self) -> str | None:
        if self._recent_projects_list is None:
            return None
        item = self._recent_projects_list.currentItem()
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        return path if isinstance(path, str) else None

    def _selected_recent_project_pinned(self) -> bool:
        if self._recent_projects_list is None or self._recent_projects_list.currentItem() is None:
            return False
        return bool(self._recent_projects_list.currentItem().data(Qt.ItemDataRole.UserRole + 1))

    def _refresh_recent_project_actions(self) -> None:
        if self._recent_clean_btn is not None:
            prefs = get_prefs()
            recent_entries = prefs.recent_projects() if hasattr(prefs, "recent_projects") else [
                {"path": path} for path in prefs.recent_files()
            ]
            has_missing = any(not Path(str(entry.get("path", "") or "")).exists() for entry in recent_entries)
            self._recent_clean_btn.setEnabled(has_missing)

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

    def _toggle_selected_recent_pin(self) -> None:
        path = self._selected_recent_project_path()
        if not path:
            return
        self._set_recent_project_pinned(path, not self._selected_recent_project_pinned())

    def _set_recent_project_pinned(self, path: str, pinned: bool) -> None:
        prefs = get_prefs()
        if hasattr(prefs, "set_recent_pinned"):
            prefs.set_recent_pinned(path, pinned)
        self._rebuild_recent_menu()

    def _remove_recent_project_entry(self, path: str) -> None:
        choice = self._dialog_message(
            "移除最近项目",
            f"确认从最近项目列表中移除「{Path(path).name}」？",
            buttons=("移除", "取消"),
        )
        if choice != "移除":
            return
        prefs = get_prefs()
        prefs.remove_recent(path)
        self._rebuild_recent_menu()

    def _clean_recent_projects(self) -> None:
        removed_any = self._prune_missing_recent_projects()
        if removed_any:
            self._rebuild_recent_menu()
        self.statusBar().showMessage("最近项目已清理", 2500)

    def _open_recent(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        now = time.monotonic()
        if (
            self._opening_recent_path == resolved
            and now - self._opening_recent_started_at < 0.6
        ):
            return
        if not self._confirm_discard():
            return
        self._opening_recent_path = resolved
        self._opening_recent_started_at = now
        try:
            if not Path(resolved).exists():
                self._dialog_warning("最近文件", f"文件不存在：\n{resolved}")
                get_prefs().remove_recent(resolved)
                self._rebuild_recent_menu()
                return
            self._begin_recent_load_feedback(resolved)
            self._do_open_json(resolved)
        finally:
            self._end_recent_load_feedback()

    def _clear_recent(self) -> None:
        get_prefs().clear_recent()
        self._rebuild_recent_menu()

    def _open_preferences(self) -> None:
        prefs = get_prefs()
        dialog_kwargs = {
            "autosave_enabled": prefs.autosave_enabled(),
            "autosave_interval": prefs.autosave_interval(),
            "recent_limit": prefs.recent_limit(),
            "show_recent_full_path": prefs.show_recent_full_path(),
            "startup_preferences": prefs.startup_preferences() if hasattr(prefs, "startup_preferences") else None,
            "editor_defaults": prefs.editor_defaults() if hasattr(prefs, "editor_defaults") else None,
            "recent_workspace_preferences": (
                prefs.recent_workspace_preferences()
                if hasattr(prefs, "recent_workspace_preferences")
                else None
            ),
            "parent": self,
        }
        try:
            dialog = PreferencesDialog(**dialog_kwargs)
        except TypeError:
            dialog = PreferencesDialog(
                autosave_enabled=dialog_kwargs["autosave_enabled"],
                autosave_interval=dialog_kwargs["autosave_interval"],
                recent_limit=dialog_kwargs["recent_limit"],
                show_recent_full_path=dialog_kwargs["show_recent_full_path"],
                parent=self,
            )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        prefs.set_autosave_enabled(bool(values["autosave_enabled"]))
        prefs.set_autosave_interval(int(values["autosave_interval"]))
        prefs.set_recent_limit(int(values["recent_limit"]))
        prefs.set_show_recent_full_path(bool(values["show_recent_full_path"]))
        if hasattr(prefs, "set_startup_preferences"):
            prefs.set_startup_preferences(dict(values.get("startup", {})))
        if hasattr(prefs, "set_editor_defaults"):
            prefs.set_editor_defaults(dict(values.get("editor_defaults", {})))
        if hasattr(prefs, "set_recent_workspace_preferences"):
            prefs.set_recent_workspace_preferences(dict(values.get("recent_workspace", {})))
        self._reset_autosave_timer()
        for table in self._channel_tables:
            self._configure_table_from_preferences(table)
        if self._recent_group is not None:
            show_recent_sidebar = True
            if hasattr(prefs, "startup_preferences"):
                show_recent_sidebar = bool(prefs.startup_preferences().get("show_recent_sidebar", True))
            self._recent_group.setHidden(self._immersive_mode or not show_recent_sidebar)
        self._rebuild_recent_menu()
        self.statusBar().showMessage("偏好设置已更新", 3000)
        self._show_toast("偏好设置", "软件偏好已保存", "success")

    def _autosave_settings(self) -> None:
        self._open_preferences()

    def _open_project_settings(self) -> None:
        dialog = ProjectSettingsDialog(editor_preferences=self._project.project_preferences, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        editor = dict(self._project.project_preferences.get("editor", {}) or {})
        editor.update(dict(values["editor"]))
        self._project.project_preferences["editor"] = editor
        self._project.project_preferences["generation_defaults"] = dict(values["generation_defaults"])
        self._project.project_preferences["phrases"] = dict(values["phrases"])
        if bool(values.get("capture_layout")) and self._channel_tables:
            self._project.project_preferences["column_layout"] = self._channel_tables[0].layout_state()
        for table in self._channel_tables:
            self._configure_table_from_preferences(table)
        self._set_modified(True)
        self._show_toast("项目设置", "项目级编辑偏好已更新", "success")

    def _reset_current_project_view(self) -> None:
        self._project.workspace_state = {}
        self._rebuild_tabs(select_index=1)
        self._set_modified(True)
        self.statusBar().showMessage("当前项目视图已重置", 3000)

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
        self._copy_tsv("IO 表", "已复制当前视图的 IO 表到剪贴板", rows)

    def _copy_symbol(self) -> None:
        assert self._tabs is not None
        if self._tabs.currentIndex() == 0:
            self._ensure_preview_fresh()
            pts = stitched_points(self._project, self._selected_preview_channel_order())
        else:
            ci = self._tabs.currentIndex() - 1
            pts = list(self._project.channels[ci].points)
        self._copy_tsv("符号表", "已复制当前视图的符号表到剪贴板", rows_symbol_table_for_points(self._project, pts))

    def _copy_d(self) -> None:
        assert self._tabs is not None
        if self._tabs.currentIndex() == 0:
            self._ensure_preview_fresh()
            pts = stitched_points(self._project, self._selected_preview_channel_order())
        else:
            ci = self._tabs.currentIndex() - 1
            pts = list(self._project.channels[ci].points)
        self._copy_tsv("D 区 CHANNEL", "已复制当前视图的 D 区 CHANNEL 到剪贴板", rows_d_channel_for_points(self._project, pts))

    def _copy_cio(self) -> None:
        assert self._tabs is not None
        if self._tabs.currentIndex() == 0:
            self._ensure_preview_fresh()
            pts = stitched_points(self._project, self._selected_preview_channel_order())
        else:
            ci = self._tabs.currentIndex() - 1
            pts = list(self._project.channels[ci].points)
        self._copy_tsv("CIO 字 CHANNEL", "已复制当前视图的 CIO 字 CHANNEL 到剪贴板", rows_cio_word_index_for_points(self._project, pts))

    def _copy_tsv(self, title: str, status_text: str, rows) -> None:
        text = tsv_from_rows(rows)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(status_text, 3000)
        self._show_toast(title, status_text, "success")

    def _copy_combined(self) -> None:
        QApplication.clipboard().setText(combined_export_text(self._project))
        status_text = "已复制全部分区合并文本到剪贴板"
        self.statusBar().showMessage(status_text, 3000)
        self._show_toast("合并全部分区", status_text, "success")

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
        renamed_points = normalize_project_auto_names(self._project)
        # 清空表格引用，防止旧表格数据覆盖新加载的项目
        self._channel_tables.clear()
        prefs = get_prefs()
        prefs.add_recent(path)
        prefs.set_last_dir(path)
        self._rebuild_recent_menu()
        self._sync_meta_from_project()
        active_tab = self._project.workspace_state.get("active_tab", "") if isinstance(self._project.workspace_state, dict) else ""
        select_index = 0 if _is_preview_tab_label(str(active_tab)) else 1
        self._rebuild_tabs(select_index=select_index)
        self._set_modified(renamed_points > 0)
        self._update_title()
        if renamed_points > 0:
            message = f"已自动更新 {renamed_points} 个名称"
            self.statusBar().showMessage(f"已打开 {path} · {message}", 5000)
            self._show_toast("自动名称", message, "info")
        else:
            self.statusBar().showMessage(f"已打开 {path}", 3000)

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
        self._capture_project_workspace_state()
        try:
            save_project_json(self._project, path)
            self._project_path = Path(path)
            prefs = get_prefs()
            prefs.add_recent(path)
            if hasattr(prefs, "mark_recent_saved"):
                prefs.mark_recent_saved(path)
            prefs.set_last_dir(path)
            self._rebuild_recent_menu()
            self._set_modified(False)
            self._update_title()
            clear_autosave()  # 成功保存后清除自动保存槽
            self.statusBar().showMessage(f"已保存 {path}", 3000)
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
        self.statusBar().showMessage(f"已导入 {n} 点", 3000)

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
        self.statusBar().showMessage(f"已导入 {n} 点", 3000)

    def _export_excel(self) -> None:
        self._flush_all_channel_tables()
        if not self._confirm_export_validation():
            return
        prefs = get_prefs()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Excel", prefs.last_dir(), "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            save_project_excel(self._project, path)
            prefs.set_last_dir(path)
            self.statusBar().showMessage(f"已导出 {path}", 3000)
        except Exception as e:
            self._dialog_error("导出失败", str(e))

    def _export_csv_io(self) -> None:
        self._flush_all_channel_tables()
        if not self._confirm_export_validation():
            return
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
            self.statusBar().showMessage(f"已导出 {path}", 3000)
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
        if hasattr(get_prefs(), "set_startup_preferences") and hasattr(get_prefs(), "startup_preferences"):
            startup = get_prefs().startup_preferences()
            if startup.get("remember_window_state", False):
                get_prefs().set_startup_preferences(
                    {
                        "saved_window_rect": [
                            self.x(),
                            self.y(),
                            self.width(),
                            self.height(),
                        ]
                    }
                )
        self._capture_project_workspace_state()
        self._autosave_timer.stop()
        self._autosave_recovery_timer.stop()
        clear_autosave()
        event.accept()
