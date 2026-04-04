# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

from .icons import load_icon


class AppTitleBar(QWidget):
    def __init__(self, window) -> None:  # noqa: ANN001
        super().__init__(window)
        self._window = window
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None

        self.setObjectName("appTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        self._menu_row = QWidget(self)
        self._menu_row.setObjectName("appTitleBarMenuRow")
        self._menu_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._menu_layout = QHBoxLayout(self._menu_row)
        self._menu_layout.setContentsMargins(0, 0, 0, 0)
        self._menu_layout.setSpacing(4)
        layout.addWidget(self._menu_row, 0)

        self._title_label = QLabel(window.windowTitle(), self)
        self._title_label.setObjectName("appTitleBarLabel")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_label, 1)

        self._min_btn = self._make_window_button("minimize-light", "最小化")
        self._max_btn = self._make_window_button("maximize-light", "最大化")
        self._close_btn = self._make_window_button("close-light", "关闭", danger=True)
        self._min_btn.clicked.connect(window.showMinimized)
        self._max_btn.clicked.connect(self._toggle_maximized)
        self._close_btn.clicked.connect(window.close)
        layout.addWidget(self._min_btn)
        layout.addWidget(self._max_btn)
        layout.addWidget(self._close_btn)

        window.windowTitleChanged.connect(self._title_label.setText)
        self.sync_window_state()

    def _make_window_button(self, icon_name: str, tooltip: str, danger: bool = False) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("appTitleBarButtonDanger" if danger else "appTitleBarButton")
        btn.setText("")
        btn.setIcon(load_icon(icon_name))
        btn.setIconSize(QSize(12, 12))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        btn.setAutoRaise(True)
        return btn

    def add_menu(self, label: str, menu: QMenu) -> None:
        btn = QToolButton(self._menu_row)
        btn.setObjectName("appTitleBarMenuButton")
        btn.setText(label)
        btn.setMinimumHeight(28)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setAutoRaise(True)
        self._menu_layout.addWidget(btn)

    def sync_window_state(self) -> None:
        maximized = self._window.isMaximized()
        self._max_btn.setIcon(load_icon("restore-light" if maximized else "maximize-light"))
        self._max_btn.setToolTip("还原" if maximized else "最大化")

    def _toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self.sync_window_state()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        child = self.childAt(event.position().toPoint())
        if child not in (None, self, self._title_label):
            super().mousePressEvent(event)
            return
        self._drag_origin = event.globalPosition().toPoint()
        self._window_origin = self._window.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if (
            self._drag_origin is None
            or self._window_origin is None
            or not (event.buttons() & Qt.MouseButton.LeftButton)
            or self._window.isMaximized()
        ):
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition().toPoint() - self._drag_origin
        self._window.move(self._window_origin + delta)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        self._drag_origin = None
        self._window_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child in (None, self, self._title_label):
                self._toggle_maximized()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)
