# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QToolBar, QToolButton

from omron_io_planner import app as app_module
from omron_io_planner.models import IoProject
from omron_io_planner.project_manager import Prefs, autosave, autosave_needs_recovery
from omron_io_planner.ui.dialogs import MessageDialog, TextInputDialog
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
    window = MainWindow()
    window._autosave_timer.stop()
    qtbot.addWidget(window)

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted()
    assert cleared == [True]


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


def test_app_main_starts_window_maximized(monkeypatch) -> None:
    shown: list[str] = []

    class _FakeApp:
        def __init__(self, argv) -> None:  # noqa: ANN001
            self.argv = argv

        def setApplicationName(self, name: str) -> None:
            self.name = name

        def exec(self) -> int:
            shown.append("exec")
            return 0

    class _FakeWindow:
        def showMaximized(self) -> None:
            shown.append("showMaximized")

    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "MainWindow", _FakeWindow)
    monkeypatch.setattr(app_module.sys, "exit", lambda code=0: shown.append(f"exit:{code}"))

    app_module.main()

    assert shown[:2] == ["showMaximized", "exec"]


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
