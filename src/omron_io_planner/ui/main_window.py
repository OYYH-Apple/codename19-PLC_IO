# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
import json
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QSplitterHandle,
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
from ..models import IoPoint, IoProject
from ..persistence import load_project_json, save_project_json, write_text_atomic
from ..project_manager import (
    autosave,
    autosave_exists,
    autosave_mtime,
    autosave_needs_recovery,
    clear_autosave,
    get_prefs,
    load_autosave,
)
from .dialogs import (
    ChoiceInputDialog,
    IntInputDialog,
    LoadingPopup,
    MessageDialog,
    PreferencesDialog,
    ProjectSettingsDialog,
    TextInputDialog,
    ToastPopup,
)
from .icons import load_icon
from .io_table_widget import IoTableWidget
from .program_workspace import ProgramWorkspace
from .style import app_stylesheet
from .window_chrome import AppTitleBar
from .zone_picker_dialog import ZonePickerDialog  # noqa: F401 — 供测试 patch 与 channels Mixin 惰性引用
from .main_window_constants import (
    APP_TITLE as _APP_TITLE,
    COL_ADDR,
    COL_COMMENT,
    COL_DTYPE,
    COL_NAME,
    COL_RACK,
    COL_USAGE,
    FALLBACK_EDITOR_DEFAULTS as _FALLBACK_EDITOR_DEFAULTS,
    LEGACY_PREVIEW_LABEL,
    PREVIEW_LABEL,
)
from .main_window_utils import (
    _deep_merge,
    _is_preview_tab_label,
    _make_action_btn,
    _make_immersive_btn,
)
from .main_window_widgets import ClickableHeader
from .main_window_find_replace import MainWindowFindReplaceMixin
from .main_window_preview_validation import MainWindowPreviewValidationMixin
from .main_window_recents_menus import MainWindowRecentsMenusMixin
from .main_window_channels import MainWindowChannelsMixin

# 左侧项目栏宽度：拖动上限为默认宽度，可双击分割条收起/展开。
_SIDEBAR_WIDTH_DEFAULT = 280
_SIDEBAR_WIDTH_MIN = 200
# 折叠后保留可点的窄条宽度（避免 hide() 导致分割手柄失效无法展开）
_SIDEBAR_COLLAPSED_STRIP = 8


class SidebarExpandRail(QFrame):
    """折叠态左侧窄条：双击请求展开（分割条在窄条右侧，仍可拖/双击）。"""

    expand_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarExpandRail")
        self.setFixedWidth(_SIDEBAR_COLLAPSED_STRIP)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("双击展开项目栏")

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.expand_requested.emit()
        super().mouseDoubleClickEvent(event)


class SplitterGripHandle(QSplitterHandle):
    """主分割条手柄：悬停时显示常见「双竖线」拖拽提示；双击切换侧栏折叠。"""

    double_clicked = Signal()

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self._hover = False
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event: QEvent) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            painter.fillRect(self.rect(), QColor("#D8E4F6"))
            line = QColor("#3D5A80")
        else:
            painter.fillRect(self.rect(), QColor("#E8EDF6"))
            line = QColor("#9AA8C0")
        painter.setPen(QPen(line, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx = int(round(self.rect().center().x()))
        cy = int(round(self.rect().center().y()))
        top, bot = cy - 10, cy + 10
        painter.drawLine(cx - 2, top, cx - 2, bot)
        painter.drawLine(cx + 2, top, cx + 2, bot)


class MainRootSplitter(QSplitter):
    """带自定义手柄的主水平分割条。"""

    handle_double_clicked = Signal()

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self.main_grip: SplitterGripHandle | None = None

    def createHandle(self) -> QSplitterHandle:
        grip = SplitterGripHandle(self.orientation(), self)
        grip.double_clicked.connect(self.handle_double_clicked.emit)
        self.main_grip = grip
        return grip


class MainWindow(
    MainWindowChannelsMixin,
    MainWindowRecentsMenusMixin,
    MainWindowPreviewValidationMixin,
    MainWindowFindReplaceMixin,
    QMainWindow,
):
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
        self._sidebar_body: QWidget | None = None
        self._sidebar_expand_rail: SidebarExpandRail | None = None
        self._recent_group: QGroupBox | None = None
        self._recent_projects_list: QListWidget | None = None
        self._recent_filter_edit: QLineEdit | None = None
        self._recent_clean_btn: QToolButton | None = None
        self._recent_click_pending_activation: str | None = None
        self._recent_menu: QMenu | None = None
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
        self._workspace_shell: QTabWidget | None = None
        self._io_workspace_page: QWidget | None = None
        self._program_workspace: ProgramWorkspace | None = None
        self._root_splitter: MainRootSplitter | None = None
        self._project_panel_collapsed = False
        self._sidebar_saved_width = _SIDEBAR_WIDTH_DEFAULT
        self._workspace_mode = "io"
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
        self._find_replace_dialog = None
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
        root = QVBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(10, 8, 10, 6)

        self._root_splitter = MainRootSplitter(Qt.Orientation.Horizontal, central)
        self._root_splitter.setObjectName("mainRootSplitter")
        self._root_splitter.setChildrenCollapsible(True)
        self._root_splitter.setHandleWidth(8)
        self._root_splitter.splitterMoved.connect(self._on_root_splitter_moved)
        self._root_splitter.handle_double_clicked.connect(self._toggle_sidebar_collapsed_from_grip)
        root.addWidget(self._root_splitter, 1)

        sidebar = QWidget(self._root_splitter)
        sidebar.setObjectName("mainSidebar")
        sidebar.setMinimumWidth(_SIDEBAR_WIDTH_MIN)
        sidebar.setMaximumWidth(_SIDEBAR_WIDTH_DEFAULT)
        self._sidebar = sidebar
        side_outer = QHBoxLayout(sidebar)
        side_outer.setContentsMargins(0, 0, 0, 0)
        side_outer.setSpacing(0)

        self._sidebar_expand_rail = SidebarExpandRail(sidebar)
        self._sidebar_expand_rail.expand_requested.connect(self._expand_sidebar_from_rail)
        self._sidebar_expand_rail.hide()

        self._sidebar_body = QWidget(sidebar)
        sidebar_layout = QVBoxLayout(self._sidebar_body)
        sidebar_layout.setSpacing(12)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        meta = QGroupBox("项目信息", self._sidebar_body)
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

        recent_group = QGroupBox("最近项目", self._sidebar_body)
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

        side_outer.addWidget(self._sidebar_expand_rail, 0)
        side_outer.addWidget(self._sidebar_body, 1)

        content = QWidget(self._root_splitter)
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        self._root_splitter.addWidget(sidebar)
        self._root_splitter.addWidget(content)
        self._root_splitter.setStretchFactor(0, 0)
        self._root_splitter.setStretchFactor(1, 1)
        self._root_splitter.setSizes([self._sidebar_saved_width, max(self.width() - self._sidebar_saved_width, 400)])

        self._workspace_shell = QTabWidget(content)
        self._workspace_shell.setObjectName("workspaceMainTabWidget")
        self._workspace_shell.setDocumentMode(True)
        self._workspace_shell.setTabPosition(QTabWidget.TabPosition.North)
        self._workspace_shell.setMovable(False)
        self._workspace_shell.setUsesScrollButtons(False)
        self._workspace_shell.tabBar().setObjectName("workspaceMainTabBar")
        layout.addWidget(self._workspace_shell, 1)

        io_page = QWidget(self._workspace_shell)
        self._io_workspace_page = io_page
        io_page_layout = QVBoxLayout(io_page)
        io_page_layout.setSpacing(12)
        io_page_layout.setContentsMargins(0, 0, 0, 0)

        copy_group = QWidget(io_page)
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
        io_page_layout.addWidget(copy_group, 0)

        # ── Tab 区 ─────────────────────────────────────────────────────────
        self._tabs = QTabWidget(io_page)
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
        io_page_layout.addWidget(self._tabs, stretch=1)

        validation_group = QGroupBox("轻量校验", io_page)
        self._validation_group = validation_group
        validation_layout = QVBoxLayout(validation_group)
        validation_layout.setContentsMargins(10, 8, 10, 8)
        validation_layout.setSpacing(6)

        validation_header = ClickableHeader(validation_group)
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
        io_page_layout.addWidget(validation_group)

        self._workspace_shell.addTab(io_page, "IO 分配")
        self._workspace_shell.setTabToolTip(0, "分区表编辑、导出与轻量校验")
        self._program_workspace = ProgramWorkspace(self._workspace_shell)
        self._program_workspace.modified.connect(lambda: self._set_modified(True))
        self._workspace_shell.addTab(self._program_workspace, "程序编辑")
        self._workspace_shell.setTabToolTip(1, "主程序 / FB、ST 与梯形图")

        # 连接
        self._btn_enter_immersive.clicked.connect(lambda: self._set_immersive_mode(not self._immersive_mode))
        self._btn_add_ch.clicked.connect(self._add_channel)
        self._btn_del_ch.clicked.connect(self._delete_current_channel)
        self._btn_copy_io.clicked.connect(self._copy_io)
        self._btn_copy_sym.clicked.connect(self._copy_symbol)
        self._btn_copy_d.clicked.connect(self._copy_d)
        self._btn_copy_cio.clicked.connect(self._copy_cio)
        self._btn_copy_all.clicked.connect(self._copy_combined)
        self._workspace_shell.currentChanged.connect(self._on_workspace_shell_tab_changed)
        self._name_edit.textChanged.connect(self._on_meta_changed)
        self._plc_edit.textChanged.connect(self._on_meta_changed)
        if self._program_workspace is not None:
            self._program_workspace.set_project(self._project)
        self._sync_workspace_mode_buttons()
        self._set_workspace_mode("io")
        self._sync_main_sidebar_visibility()
        self._sync_immersive_corner_button()
        self._sync_channel_action_buttons()

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

    def _on_workspace_shell_tab_changed(self, index: int) -> None:
        want = "program" if index == 1 else "io"
        if want == self._workspace_mode:
            return
        self._set_workspace_mode(want)

    def _expand_sidebar_from_rail(self) -> None:
        if self._immersive_mode or not self._project_panel_collapsed:
            return
        self._project_panel_collapsed = False
        self._sync_main_sidebar_visibility()

    def _toggle_sidebar_collapsed_from_grip(self) -> None:
        if self._immersive_mode:
            return
        if (
            not self._project_panel_collapsed
            and self._root_splitter is not None
            and self._sidebar is not None
            and self._sidebar.isVisible()
        ):
            sizes = self._root_splitter.sizes()
            if sizes and sizes[0] >= _SIDEBAR_WIDTH_MIN:
                self._sidebar_saved_width = min(sizes[0], _SIDEBAR_WIDTH_DEFAULT)
        self._project_panel_collapsed = not self._project_panel_collapsed
        self._sync_main_sidebar_visibility()

    def _on_root_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._root_splitter is None or self._sidebar is None or not self._sidebar.isVisible():
            return
        if self._immersive_mode:
            return
        sizes = self._root_splitter.sizes()
        if len(sizes) < 1:
            return
        w0 = sizes[0]
        if self._project_panel_collapsed:
            if w0 >= _SIDEBAR_WIDTH_MIN:
                self._sidebar_saved_width = min(w0, _SIDEBAR_WIDTH_DEFAULT)
                self._project_panel_collapsed = False
                self._sync_main_sidebar_visibility()
            return
        if w0 >= _SIDEBAR_WIDTH_MIN:
            self._sidebar_saved_width = min(w0, _SIDEBAR_WIDTH_DEFAULT)

    def _sync_main_sidebar_visibility(self) -> None:
        if self._sidebar is None or self._root_splitter is None:
            return
        if self._immersive_mode:
            self._sidebar.hide()
        elif self._project_panel_collapsed:
            self._sidebar.show()
            if self._sidebar_body is not None:
                self._sidebar_body.hide()
            if self._sidebar_expand_rail is not None:
                self._sidebar_expand_rail.show()
            self._sidebar.setMinimumWidth(_SIDEBAR_COLLAPSED_STRIP)
            self._sidebar.setMaximumWidth(_SIDEBAR_COLLAPSED_STRIP)
            total = max(self._root_splitter.width(), 520)
            self._root_splitter.blockSignals(True)
            self._root_splitter.setSizes([_SIDEBAR_COLLAPSED_STRIP, total - _SIDEBAR_COLLAPSED_STRIP])
            self._root_splitter.blockSignals(False)
        else:
            self._sidebar.show()
            if self._sidebar_expand_rail is not None:
                self._sidebar_expand_rail.hide()
            if self._sidebar_body is not None:
                self._sidebar_body.show()
            self._sidebar.setMinimumWidth(_SIDEBAR_WIDTH_MIN)
            self._sidebar.setMaximumWidth(_SIDEBAR_WIDTH_DEFAULT)
            total = max(self._root_splitter.width(), 520)
            w = max(_SIDEBAR_WIDTH_MIN, min(self._sidebar_saved_width, _SIDEBAR_WIDTH_DEFAULT))
            self._root_splitter.blockSignals(True)
            self._root_splitter.setSizes([w, total - w])
            self._root_splitter.blockSignals(False)
        self._refresh_main_splitter_grip_tooltip()

    def _refresh_main_splitter_grip_tooltip(self) -> None:
        sp = self._root_splitter
        if sp is None or sp.main_grip is None:
            return
        grip = sp.main_grip
        if self._immersive_mode:
            grip.setToolTip("沉浸模式下左侧项目栏已隐藏；请先退出沉浸模式后再调整。")
        elif self._project_panel_collapsed:
            grip.setToolTip(
                "双击分割条或左侧窄条展开「项目信息 / 最近项目」。也可向右拖动分割条拉宽后自动展开。"
            )
        else:
            grip.setToolTip(
                "拖动调整左侧区域宽度（最宽不超过默认宽度）。双击分割条收起侧栏（保留窄条，可再双击展开）。"
            )

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
            write_text_atomic(path, text, encoding="utf-8-sig", newline=None)
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
