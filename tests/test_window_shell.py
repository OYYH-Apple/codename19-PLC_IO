# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QToolBar, QToolButton

from omron_io_planner import app as app_module
from omron_io_planner.models import IoProject
from omron_io_planner.persistence import load_project_json, save_project_json
from omron_io_planner.project_manager import Prefs, autosave, autosave_needs_recovery
from omron_io_planner.ui.dialogs import MessageDialog, TextInputDialog
from omron_io_planner.ui.icons import load_icon
from omron_io_planner.ui.main_window import MainWindow
from omron_io_planner.ui.style import app_stylesheet
from omron_io_planner.ui.window_chrome import AppTitleBar


def _make_window(qtbot, monkeypatch) -> MainWindow:
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    window = MainWindow()
    window._confirm_discard = lambda: True
    window._autosave_timer.stop()
    qtbot.addWidget(window)
    return window


def test_autosave_snapshot_is_ignored_when_saved_file_is_newer(tmp_path, monkeypatch) -> None:
    autosave_path = tmp_path / "autosave.json"
    project_path = tmp_path / "saved.json"
    monkeypatch.setattr("omron_io_planner.project_manager._AUTOSAVE_FILE", autosave_path)

    autosave(IoProject(name="demo"), project_path)
    project_path.write_text("{}", encoding="utf-8")
    newer = autosave_path.stat().st_mtime + 10
    os.utime(project_path, (newer, newer))

    assert not autosave_needs_recovery()


def test_close_event_clears_autosave_when_project_is_clean(qtbot, monkeypatch) -> None:
    cleared: list[bool] = []
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    monkeypatch.setattr("omron_io_planner.ui.main_window.clear_autosave", lambda: cleared.append(True))
    window = _make_window(qtbot, monkeypatch)

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted()
    assert cleared == [True]
    window.deleteLater()
    QApplication.processEvents()


def test_clear_recovery_record_shows_success_feedback(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    seen: list[tuple[str, str, str]] = []
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: True)
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_needs_recovery", lambda: True)
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_mtime", lambda: 0.0)
    monkeypatch.setattr(window, "_dialog_message", lambda *args, **kwargs: "清除记录")
    monkeypatch.setattr("omron_io_planner.ui.main_window.clear_autosave", lambda: True)
    monkeypatch.setattr(window, "_show_toast", lambda title, text, kind="info": seen.append((title, text, kind)))

    window._check_autosave_recovery()

    assert window.statusBar().currentMessage() == "已清除恢复记录"
    assert seen == [("恢复记录", "自动保存记录已清除", "success")]


def test_main_window_uses_custom_frameless_title_bar(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert isinstance(window.menuWidget(), AppTitleBar)
    assert window.menuWidget().testAttribute(Qt.WidgetAttribute.WA_StyledBackground)


def test_main_window_has_single_ctrl_s_action(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    save_shortcut = QKeySequence(QKeySequence.StandardKey.Save).toString()
    save_actions = [
        action for action in window.findChildren(QAction)
        if action.shortcut().toString() == save_shortcut
    ]

    assert len(save_actions) == 1


def test_main_window_resize_hit_testing_covers_edges_and_corners(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window.resize(1200, 800)

    top_left = window._resize_edges_for_pos(window.rect().topLeft() + QPoint(1, 1))
    right_edge = window._resize_edges_for_pos(QPoint(window.width() - 1, window.height() // 2))
    center = window._resize_edges_for_pos(QPoint(window.width() // 2, window.height() // 2))

    assert top_left == (Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
    assert right_edge == Qt.Edge.RightEdge
    assert center is None


def test_resize_cursor_shape_accepts_single_edge_values(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    assert window._resize_cursor_shape(Qt.Edge.LeftEdge) == Qt.CursorShape.SizeHorCursor
    assert (
        window._resize_cursor_shape(Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
        == Qt.CursorShape.SizeFDiagCursor
    )


def test_startup_does_not_prompt_autosave_recovery_and_prunes_missing_recents(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text("{}", encoding="utf-8")
    missing = tmp_path / "missing.json"

    class _FakePrefs:
        def __init__(self) -> None:
            self._recent = [str(valid), str(missing)]

        def recent_files(self) -> list[str]:
            return list(self._recent)

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            self._recent = [entry for entry in self._recent if entry != str(path)]

        def clear_recent(self) -> None:
            self._recent = []

        def recent_limit(self) -> int:
            return 10

        def show_recent_full_path(self) -> bool:
            return False

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

    prefs = _FakePrefs()
    recovery_prompts: list[tuple[str, str]] = []
    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: prefs)
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: True)
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_needs_recovery", lambda: True)
    monkeypatch.setattr(
        MainWindow,
        "_dialog_message",
        lambda self, title, text, buttons=("确定",): recovery_prompts.append((title, text)) or "忽略",
    )

    window = MainWindow()
    window._autosave_timer.stop()
    qtbot.addWidget(window)
    qtbot.wait(300)

    assert recovery_prompts == []
    assert prefs.recent_files() == [str(valid)]


def test_title_bar_menu_indicator_uses_right_center_alignment() -> None:
    stylesheet = app_stylesheet()

    assert "#appTitleBarMenuButton::menu-indicator" in stylesheet
    assert "subcontrol-position: right center;" in stylesheet


def test_main_window_toolbar_actions_use_icons_and_no_emoji_labels(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    banned = "🆕📂💾📥📤📋📊🔄🗑＋－✕□❐"
    interesting = {"新建", "打开 JSON…", "保存 JSON", "导入 Excel…", "导出 Excel…"}

    actions = [action for action in window.findChildren(QAction) if action.text() in interesting]

    assert actions
    for action in actions:
        assert action.icon().isNull() is False
        assert not any(ch in banned for ch in action.text())


def test_title_bar_window_controls_use_icons_not_text(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    title_bar = window.menuWidget()

    assert isinstance(title_bar, AppTitleBar)
    for button in (title_bar._min_btn, title_bar._max_btn, title_bar._close_btn):
        assert button.icon().isNull() is False
        assert button.text() == ""


def test_main_window_labels_use_point_sized_fonts(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    labels = [label for label in window.findChildren(QLabel) if label.text()]

    assert labels
    assert all(label.font().pointSize() > 0 for label in labels)


def test_toolbar_shows_text_beside_white_icons(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    toolbar = window.findChild(QToolBar)
    buttons = toolbar.findChildren(QToolButton, options=Qt.FindChildOption.FindDirectChildrenOnly)

    assert toolbar is not None
    assert toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    assert buttons
    assert any(button.text() == "新建" for button in buttons)
    assert all(button.icon().isNull() is False for button in buttons if button.text())


def test_immersive_action_uses_white_focus_icon(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    immersive_action = next(action for action in window.findChildren(QAction) if action.text() == "沉浸模式")

    assert immersive_action.icon().cacheKey() == load_icon("focus-light").cacheKey()


def test_prefs_recent_limit_trims_recent_file_count(tmp_path, monkeypatch) -> None:
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr("omron_io_planner.project_manager._PREFS_FILE", prefs_path)
    prefs = Prefs()
    prefs.set_recent_limit(2)

    prefs.add_recent(tmp_path / "a.json")
    prefs.add_recent(tmp_path / "b.json")
    prefs.add_recent(tmp_path / "c.json")

    assert prefs.recent_files() == [
        str((tmp_path / "c.json").resolve()),
        str((tmp_path / "b.json").resolve()),
    ]


def test_main_window_preferences_updates_prefs_and_recent_sidebar(qtbot, monkeypatch) -> None:
    class _FakePrefs:
        def __init__(self) -> None:
            self.enabled = True
            self.interval = 120
            self.limit = 10
            self.show_full = False
            self.set_calls: list[tuple[str, object]] = []

        def autosave_enabled(self) -> bool:
            return self.enabled

        def set_autosave_enabled(self, value: bool) -> None:
            self.enabled = value
            self.set_calls.append(("autosave_enabled", value))

        def autosave_interval(self) -> int:
            return self.interval

        def set_autosave_interval(self, value: int) -> None:
            self.interval = value
            self.set_calls.append(("autosave_interval", value))

        def recent_limit(self) -> int:
            return self.limit

        def set_recent_limit(self, value: int) -> None:
            self.limit = value
            self.set_calls.append(("recent_limit", value))

        def show_recent_full_path(self) -> bool:
            return self.show_full

        def set_show_recent_full_path(self, value: bool) -> None:
            self.show_full = value
            self.set_calls.append(("show_recent_full_path", value))

        def recent_files(self) -> list[str]:
            return []

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

    class _FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, *, autosave_enabled, autosave_interval, recent_limit, show_recent_full_path, parent=None):
            self._values = {
                "autosave_enabled": False,
                "autosave_interval": 300,
                "recent_limit": 6,
                "show_recent_full_path": True,
            }

        def exec(self) -> int:
            return self.DialogCode.Accepted

        def values(self) -> dict[str, object]:
            return dict(self._values)

    prefs = _FakePrefs()
    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: prefs)
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    monkeypatch.setattr("omron_io_planner.ui.main_window.PreferencesDialog", _FakeDialog)
    window = MainWindow()
    window._autosave_timer.stop()
    qtbot.addWidget(window)

    window._open_preferences()

    assert ("autosave_enabled", False) in prefs.set_calls
    assert ("autosave_interval", 300) in prefs.set_calls
    assert ("recent_limit", 6) in prefs.set_calls
    assert ("show_recent_full_path", True) in prefs.set_calls


def test_app_main_starts_window_centered_with_default_geometry(monkeypatch) -> None:
    shown: list[object] = []

    class _FakeApp:
        def __init__(self, argv) -> None:  # noqa: ANN001
            self.argv = argv

        def setApplicationName(self, name: str) -> None:
            self.name = name

        def setWindowIcon(self, icon) -> None:  # noqa: ANN001
            self.icon = icon

        def exec(self) -> int:
            shown.append("exec")
            return 0

        class _FakeScreen:
            def availableGeometry(self) -> QRect:
                return QRect(0, 0, 2560, 1440)

        def primaryScreen(self):  # noqa: ANN001
            return self._FakeScreen()

    class _FakeWindow:
        def __init__(self) -> None:
            self.width_value = 0
            self.height_value = 0

        def setWindowIcon(self, icon) -> None:  # noqa: ANN001
            self.icon = icon

        def resize(self, width: int, height: int) -> None:
            self.width_value = width
            self.height_value = height
            shown.append(("resize", width, height))

        def width(self) -> int:
            return self.width_value

        def height(self) -> int:
            return self.height_value

        def move(self, x: int, y: int) -> None:
            shown.append(("move", x, y))

        def show(self) -> None:
            shown.append("show")

    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "MainWindow", _FakeWindow)
    monkeypatch.setattr(app_module.sys, "exit", lambda code=0: shown.append(f"exit:{code}"))

    app_module.main()

    assert ("resize", 2125, 1238) in shown
    assert ("move", 217, 101) in shown
    assert shown[-2:] == ["exec", "exit:0"]


def test_custom_message_dialog_is_frameless(qtbot) -> None:
    dialog = MessageDialog("提示", "内容", buttons=["确定"])
    qtbot.addWidget(dialog)

    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.objectName() == "appMessageDialog"
    assert dialog._title_bar.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)


def test_custom_text_input_dialog_is_frameless(qtbot) -> None:
    dialog = TextInputDialog("重命名", "分区名称:", "CIO 区")
    qtbot.addWidget(dialog)

    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.objectName() == "appTextInputDialog"


def test_save_json_success_shows_success_toast(qtbot, monkeypatch, tmp_path) -> None:
    window = _make_window(qtbot, monkeypatch)
    seen: list[tuple[str, str, str]] = []
    monkeypatch.setattr("omron_io_planner.ui.main_window.clear_autosave", lambda: None)
    monkeypatch.setattr("omron_io_planner.ui.main_window.save_project_json", lambda project, path: None)
    monkeypatch.setattr(window, "_show_toast", lambda title, text, kind="info": seen.append((title, text, kind)))

    window._do_save_json(str(tmp_path / "demo.json"))

    assert seen
    assert seen[-1][0] == "保存成功"
    assert seen[-1][2] == "success"


def test_copy_buttons_show_success_toast(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    seen: list[tuple[str, str, str]] = []
    monkeypatch.setattr(window, "_show_toast", lambda title, text, kind="info": seen.append((title, text, kind)))

    actions = [
        (window._btn_copy_io, ("IO 表", "已复制当前视图的 IO 表到剪贴板", "success")),
        (window._btn_copy_sym, ("符号表", "已复制当前视图的符号表到剪贴板", "success")),
        (window._btn_copy_d, ("D 区 CHANNEL", "已复制当前视图的 D 区 CHANNEL 到剪贴板", "success")),
        (window._btn_copy_cio, ("CIO 字 CHANNEL", "已复制当前视图的 CIO 字 CHANNEL 到剪贴板", "success")),
        (window._btn_copy_all, ("合并全部分区", "已复制全部分区合并文本到剪贴板", "success")),
    ]

    for button, expected in actions:
        assert button is not None
        button.click()

    assert seen == [expected for _button, expected in actions]


def test_save_json_failure_uses_save_failure_prompt(qtbot, monkeypatch, tmp_path) -> None:
    window = _make_window(qtbot, monkeypatch)
    errors: list[tuple[str, str]] = []

    def _boom(project, path) -> None:  # noqa: ANN001
        raise RuntimeError("磁盘不可写")

    monkeypatch.setattr("omron_io_planner.ui.main_window.save_project_json", _boom)
    monkeypatch.setattr(window, "_dialog_error", lambda title, text: errors.append((title, text)))
    monkeypatch.setattr(window, "_show_toast", lambda *args, **kwargs: None)

    window._do_save_json(str(tmp_path / "demo.json"))

    assert errors == [("保存失败", "磁盘不可写")]


def test_project_json_roundtrip_preserves_workspace_and_project_preferences(tmp_path) -> None:
    path = tmp_path / "project.json"
    project = IoProject(name="demo")
    project.project_preferences = {
        "editor": {"continuous_entry": True, "default_immersive": True},
        "phrases": {"comment": ["阻挡气缸伸出到位", "阻挡气缸缩回到位"]},
        "generation_defaults": {"row_count": 8, "name_template": "X{n:02}"},
    }
    project.workspace_state = {
        "active_tab": "CIO 区",
        "preview_order": ["WR 区", "CIO 区"],
        "preview_checked": ["WR 区"],
        "table_layout": {"widths": [80, 100, 120, 420, 100, 88]},
    }

    save_project_json(project, path)
    loaded = load_project_json(path)

    assert loaded.project_preferences["editor"]["continuous_entry"] is True
    assert loaded.project_preferences["phrases"]["comment"][0] == "阻挡气缸伸出到位"
    assert loaded.workspace_state["preview_order"] == ["WR 区", "CIO 区"]


def test_prefs_recent_project_entries_sort_pinned_before_recent(tmp_path, monkeypatch) -> None:
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr("omron_io_planner.project_manager._PREFS_FILE", prefs_path)
    prefs = Prefs()
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text("{}", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")

    prefs.add_recent(a)
    prefs.add_recent(b)
    prefs.set_recent_pinned(a, True)

    entries = prefs.recent_projects()

    assert [Path(entry["path"]).name for entry in entries[:2]] == ["a.json", "b.json"]
    assert entries[0]["pinned"] is True
