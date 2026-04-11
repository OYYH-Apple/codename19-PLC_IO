# -*- coding: utf-8 -*-
"""主窗口专用小型控件（最近项目行、可点击标题等）。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import load_icon


class RecentProjectItemWidget(QWidget):
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


class ClickableHeader(QWidget):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
