# -*- coding: utf-8 -*-
"""应用程序入口。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .project_manager import get_prefs
from .ui.main_window import MainWindow


_STARTUP_RATIO = (0.83, 0.86)


def _resolve_app_icon_path() -> Path | None:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", "")
        bundled_logo = Path(bundle_root) / "logo.png" if bundle_root else None
        if bundled_logo is not None and bundled_logo.is_file():
            return bundled_logo
    repo_logo = Path(__file__).resolve().parents[2] / "logo.png"
    if repo_logo.is_file():
        return repo_logo
    return None


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("欧姆龙 IO 分配助手")
    icon_path = _resolve_app_icon_path()
    app_icon = QIcon(str(icon_path)) if icon_path is not None else QIcon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    w = MainWindow()
    if not app_icon.isNull():
        w.setWindowIcon(app_icon)
    screen = app.primaryScreen()
    prefs = get_prefs()
    startup = prefs.startup_preferences() if hasattr(prefs, "startup_preferences") else {}
    saved_rect = startup.get("saved_window_rect", []) if isinstance(startup, dict) else []
    if (
        bool(startup.get("remember_window_state", False))
        and isinstance(saved_rect, list)
        and len(saved_rect) == 4
    ):
        w.resize(int(saved_rect[2]), int(saved_rect[3]))
        w.move(int(saved_rect[0]), int(saved_rect[1]))
    elif screen is not None:
        available = screen.availableGeometry()
        width = round(available.width() * _STARTUP_RATIO[0])
        height = round(available.height() * _STARTUP_RATIO[1])
        w.resize(width, height)
        x_pos = available.x() + max(0, (available.width() - w.width()) // 2)
        y_pos = available.y() + max(0, (available.height() - w.height()) // 2)
        w.move(x_pos, y_pos)
    else:
        w.resize(1594, 929)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
