# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from omron_io_planner.models import IoProject
from omron_io_planner.program_models import FunctionBlock, ProgramUnit
from omron_io_planner.ui.main_window import MainWindow
from omron_io_planner.ui.program_workspace import ProgramWorkspace


def _make_window(qtbot, monkeypatch) -> MainWindow:
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)

    class _TestPrefs:
        def startup_preferences(self) -> dict[str, object]:
            return {
                "remember_window_state": False,
                "saved_window_rect": [],
                "auto_open_recent": False,
                "show_recent_sidebar": True,
            }

        def recent_workspace_preferences(self) -> dict[str, object]:
            return {"auto_prune_missing": False, "allow_pinned": True}

        def editor_defaults(self) -> dict[str, object]:
            return {}

        def recent_files(self) -> list[str]:
            return []

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return ""

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def show_recent_full_path(self) -> bool:
            return False

    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: _TestPrefs())
    window = MainWindow()
    window._confirm_discard = lambda: True
    window._autosave_timer.stop()
    qtbot.addWidget(window)
    return window


def test_program_workspace_restores_selected_item(qtbot) -> None:
    workspace = ProgramWorkspace()
    qtbot.addWidget(workspace)
    project = IoProject(
        programs=[ProgramUnit(uid="main-1", name="主程序 1")],
        function_blocks=[FunctionBlock(uid="fb-1", name="AxisHome")],
        workspace_state={"program_workspace": {"selected_item": "fb:fb-1:variables"}},
    )

    workspace.set_project(project)

    assert workspace.current_item_key() == "fb:fb-1:variables"
    assert "主程序 1" in workspace.item_labels()
    assert "AxisHome / 变量定义" in workspace.item_labels()


def test_main_window_exposes_program_workspace_entry(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    buttons = [button for button in window.findChildren(QPushButton) if button.text() in {"IO 分配", "程序编辑"}]

    assert {button.text() for button in buttons} == {"IO 分配", "程序编辑"}

    window._set_workspace_mode("program")
    QApplication.processEvents()

    assert window._workspace_mode == "program"
    assert window._program_workspace is not None
