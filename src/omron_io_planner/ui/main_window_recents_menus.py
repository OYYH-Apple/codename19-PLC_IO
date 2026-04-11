# -*- coding: utf-8 -*-
"""主窗口：主菜单 / 工具栏与最近项目（Mixin）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QLineEdit, QMenu, QToolBar, QToolButton

from .icons import load_icon
from .main_window_widgets import RecentProjectItemWidget
from .window_chrome import AppTitleBar


def _get_prefs():
    """与 `main_window` 中同名符号一致，便于测试 monkeypatch `omron_io_planner.ui.main_window.get_prefs`。"""
    from omron_io_planner.ui import main_window as main_window_module

    return main_window_module.get_prefs()


def _monotonic() -> float:
    """与 `main_window.time` 一致，便于测试 monkeypatch `omron_io_planner.ui.main_window.time.monotonic`。"""
    from omron_io_planner.ui import main_window as main_window_module

    return main_window_module.time.monotonic()


class MainWindowRecentsMenusMixin:
    _title_bar: AppTitleBar | None
    _toolbar: QToolBar | None
    _immersive_action: QAction | None
    _recent_menu: QMenu | None
    _recent_projects_list: QListWidget | None
    _recent_filter_edit: QLineEdit | None
    _recent_clean_btn: QToolButton | None
    _recent_click_pending_activation: str | None
    _project_path: Path | None
    _opening_recent_path: str | None
    _opening_recent_started_at: float

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

        self._recent_menu = QMenu("最近文件(&R)", file_menu)
        file_menu.addMenu(self._recent_menu)
        self._rebuild_recent_menu()

        file_menu.addSeparator()
        file_menu.addAction(actions["quit"])

        edit_menu.addAction(actions["preferences"])
        edit_menu.addAction(actions["project_settings"])
        edit_menu.addAction(actions["reset_project_view"])
        edit_menu.addSeparator()
        edit_menu.addAction(actions["find"])
        edit_menu.addAction(actions["replace"])
        edit_menu.addAction(actions["focus_filter"])

        view_menu.addAction(actions["immersive"])

    def _rebuild_recent_menu(self) -> None:
        """重建"最近文件"子菜单。"""
        recent_prefs = _get_prefs()
        recent_workspace = (
            recent_prefs.recent_workspace_preferences()
            if hasattr(recent_prefs, "recent_workspace_preferences")
            else {"auto_prune_missing": True}
        )
        if recent_workspace.get("auto_prune_missing", True):
            self._prune_missing_recent_projects()
        if self._recent_menu is None:
            return
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
                act.triggered.connect(lambda checked=False, path=p: self._open_recent(path))
            self._recent_menu.addSeparator()
            self._recent_menu.addAction("清空最近文件", self._clear_recent)
        self._rebuild_recent_projects_list()

    def _prune_missing_recent_projects(self) -> bool:
        prefs = _get_prefs()
        removed_any = False
        for path in list(prefs.recent_files()):
            if not Path(path).exists():
                prefs.remove_recent(path)
                removed_any = True
        return removed_any

    def _rebuild_recent_projects_list(self) -> None:
        if self._recent_projects_list is None:
            return
        prefs = _get_prefs()
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
            widget = RecentProjectItemWidget(
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
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str) and path:
            self._recent_click_pending_activation = path
            self._open_recent(path)

    def _on_recent_project_activated(self, item: QListWidgetItem) -> None:
        if item is None:
            return
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
            prefs = _get_prefs()
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
        _get_prefs().remove_recent(path)
        self._rebuild_recent_menu()

    def _toggle_selected_recent_pin(self) -> None:
        path = self._selected_recent_project_path()
        if not path:
            return
        self._set_recent_project_pinned(path, not self._selected_recent_project_pinned())

    def _set_recent_project_pinned(self, path: str, pinned: bool) -> None:
        prefs = _get_prefs()
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
        prefs = _get_prefs()
        prefs.remove_recent(path)
        self._rebuild_recent_menu()

    def _clean_recent_projects(self) -> None:
        removed_any = self._prune_missing_recent_projects()
        if removed_any:
            self._rebuild_recent_menu()
        self.statusBar().showMessage("最近项目已清理", 2500)

    def _open_recent(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        now = _monotonic()
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
                _get_prefs().remove_recent(resolved)
                self._rebuild_recent_menu()
                return
            self._begin_recent_load_feedback(resolved)
            self._do_open_json(resolved)
        finally:
            self._end_recent_load_feedback()

    def _clear_recent(self) -> None:
        _get_prefs().clear_recent()
        self._rebuild_recent_menu()
