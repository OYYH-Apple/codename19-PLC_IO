# -*- coding: utf-8 -*-
"""应用程序入口。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


_STARTUP_RATIO = (0.83, 0.86)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("欧姆龙 IO 分配助手")
    w = MainWindow()
    screen = app.primaryScreen()
    if screen is not None:
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
