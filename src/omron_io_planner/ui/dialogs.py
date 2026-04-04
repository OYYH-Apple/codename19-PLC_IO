# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class _DialogTitleBar(QWidget):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None
        self.setObjectName("appDialogTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 8)
        layout.setSpacing(8)

        self._title = QLabel(title, self)
        self._title.setObjectName("appDialogTitleLabel")
        layout.addWidget(self._title, 1)

        close_btn = QPushButton("✕", self)
        close_btn.setObjectName("appDialogCloseButton")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(lambda: self.window().reject())
        layout.addWidget(close_btn)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_origin = event.globalPosition().toPoint()
        self._window_origin = self.window().frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if (
            self._drag_origin is None
            or self._window_origin is None
            or not (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition().toPoint() - self._drag_origin
        self.window().move(self._window_origin + delta)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        self._drag_origin = None
        self._window_origin = None
        super().mouseReleaseEvent(event)


class AppDialog(QDialog):
    def __init__(self, title: str, *, object_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowSystemMenuHint
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._frame = QFrame(self)
        self._frame.setObjectName("appDialogFrame")
        self._frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self._frame)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self._title_bar = _DialogTitleBar(title, self._frame)
        frame_layout.addWidget(self._title_bar)

        self._body = QWidget(self._frame)
        self._body.setObjectName("appDialogBody")
        self._body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(16, 12, 16, 16)
        self._body_layout.setSpacing(12)
        frame_layout.addWidget(self._body)


class MessageDialog(AppDialog):
    def __init__(self, title: str, message: str, *, buttons: list[str] | tuple[str, ...], parent=None) -> None:
        super().__init__(title, object_name="appMessageDialog", parent=parent)
        self._choice: str | None = None
        self.setMinimumWidth(360)

        body = QLabel(message, self._body)
        body.setWordWrap(True)
        body.setObjectName("appDialogMessage")
        self._body_layout.addWidget(body)

        button_row = QHBoxLayout()
        button_row.addStretch()
        for label in buttons:
            btn = QPushButton(label, self._body)
            btn.setProperty("dialogRole", label)
            btn.clicked.connect(lambda _checked=False, current=label: self._finish(current))
            button_row.addWidget(btn)
        self._body_layout.addLayout(button_row)

    def _finish(self, label: str) -> None:
        self._choice = label
        self.accept()

    def choice(self) -> str | None:
        return self._choice


class TextInputDialog(AppDialog):
    def __init__(self, title: str, label: str, text: str = "", parent=None) -> None:
        super().__init__(title, object_name="appTextInputDialog", parent=parent)
        self.setMinimumWidth(380)

        prompt = QLabel(label, self._body)
        prompt.setWordWrap(True)
        self._body_layout.addWidget(prompt)

        self._edit = QLineEdit(self._body)
        self._edit.setText(text)
        self._body_layout.addWidget(self._edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._body,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._body_layout.addWidget(btns)

    def value(self) -> str:
        return self._edit.text()

    @classmethod
    def get_text(cls, parent, title: str, label: str, text: str = "") -> tuple[str, bool]:  # noqa: ANN001
        dialog = cls(title, label, text, parent)
        ok = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.value(), ok


class ChoiceInputDialog(AppDialog):
    def __init__(self, title: str, label: str, items: list[str], current_index: int = 0, parent=None) -> None:
        super().__init__(title, object_name="appChoiceInputDialog", parent=parent)
        self.setMinimumWidth(380)

        prompt = QLabel(label, self._body)
        prompt.setWordWrap(True)
        self._body_layout.addWidget(prompt)

        self._combo = QComboBox(self._body)
        self._combo.addItems(items)
        self._combo.setCurrentIndex(max(0, min(current_index, len(items) - 1)) if items else -1)
        self._body_layout.addWidget(self._combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._body,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._body_layout.addWidget(btns)

    def value(self) -> str:
        return self._combo.currentText()

    @classmethod
    def get_item(
        cls,
        parent,
        title: str,
        label: str,
        items: list[str],
        current_index: int = 0,
    ) -> tuple[str, bool]:  # noqa: ANN001
        dialog = cls(title, label, items, current_index, parent)
        ok = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.value(), ok


class IntInputDialog(AppDialog):
    def __init__(
        self,
        title: str,
        label: str,
        value: int,
        minimum: int,
        maximum: int,
        parent=None,
    ) -> None:
        super().__init__(title, object_name="appIntInputDialog", parent=parent)
        self.setMinimumWidth(380)

        prompt = QLabel(label, self._body)
        prompt.setWordWrap(True)
        self._body_layout.addWidget(prompt)

        self._spin = QSpinBox(self._body)
        self._spin.setRange(minimum, maximum)
        self._spin.setValue(value)
        self._body_layout.addWidget(self._spin)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._body,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._body_layout.addWidget(btns)

    def value(self) -> int:
        return int(self._spin.value())

    @classmethod
    def get_int(
        cls,
        parent,
        title: str,
        label: str,
        value: int,
        minimum: int,
        maximum: int,
    ) -> tuple[int, bool]:  # noqa: ANN001
        dialog = cls(title, label, value, minimum, maximum, parent)
        ok = dialog.exec() == QDialog.DialogCode.Accepted
        return dialog.value(), ok


class PreferencesDialog(AppDialog):
    def __init__(
        self,
        *,
        autosave_enabled: bool,
        autosave_interval: int,
        recent_limit: int,
        show_recent_full_path: bool,
        parent=None,
    ) -> None:
        super().__init__("软件偏好设置", object_name="appPreferencesDialog", parent=parent)
        self.setMinimumWidth(440)

        intro = QLabel("配置自动保存和最近项目栏的展示方式。", self._body)
        intro.setWordWrap(True)
        self._body_layout.addWidget(intro)

        autosave_group = QGroupBox("自动保存", self._body)
        autosave_form = QFormLayout(autosave_group)
        autosave_form.setHorizontalSpacing(12)
        autosave_form.setVerticalSpacing(8)
        self._autosave_enabled = QCheckBox("启用自动保存", autosave_group)
        self._autosave_enabled.setChecked(autosave_enabled)
        self._autosave_interval = QSpinBox(autosave_group)
        self._autosave_interval.setRange(30, 3600)
        self._autosave_interval.setSuffix(" 秒")
        self._autosave_interval.setValue(autosave_interval)
        autosave_form.addRow(self._autosave_enabled)
        autosave_form.addRow("保存间隔", self._autosave_interval)
        self._body_layout.addWidget(autosave_group)

        recent_group = QGroupBox("最近项目栏", self._body)
        recent_form = QFormLayout(recent_group)
        recent_form.setHorizontalSpacing(12)
        recent_form.setVerticalSpacing(8)
        self._recent_limit = QSpinBox(recent_group)
        self._recent_limit.setRange(1, 30)
        self._recent_limit.setValue(recent_limit)
        self._show_recent_full_path = QCheckBox("显示完整路径", recent_group)
        self._show_recent_full_path.setChecked(show_recent_full_path)
        recent_form.addRow("最近项目数量", self._recent_limit)
        recent_form.addRow(self._show_recent_full_path)
        self._body_layout.addWidget(recent_group)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._body,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._body_layout.addWidget(btns)

    def values(self) -> dict[str, object]:
        return {
            "autosave_enabled": self._autosave_enabled.isChecked(),
            "autosave_interval": int(self._autosave_interval.value()),
            "recent_limit": int(self._recent_limit.value()),
            "show_recent_full_path": self._show_recent_full_path.isChecked(),
        }


class ToastPopup(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("appToast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self._title = QLabel("", self)
        self._title.setObjectName("appToastTitle")
        layout.addWidget(self._title)

        self._message = QLabel("", self)
        self._message.setObjectName("appToastMessage")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._timer = self.startTimer(0)
        self.killTimer(self._timer)
        self._timer = 0

    def show_message(self, title: str, message: str, kind: str = "info", timeout_ms: int = 2200) -> None:
        self.setProperty("toastKind", kind)
        self.style().unpolish(self)
        self.style().polish(self)
        self._title.setText(title)
        self._message.setText(message)
        self.adjustSize()

        parent = self.parentWidget()
        if parent is not None:
            margin = 18
            x_pos = max(margin, parent.width() - self.width() - margin)
            y_pos = margin + 48
            self.move(x_pos, y_pos)

        self.show()
        self.raise_()
        if self._timer:
            self.killTimer(self._timer)
        self._timer = self.startTimer(timeout_ms)

    def timerEvent(self, event) -> None:  # noqa: ANN001
        if event.timerId() == self._timer:
            self.killTimer(self._timer)
            self._timer = 0
            self.hide()


class LoadingPopup(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("appLoadingPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        self._title = QLabel("", self)
        self._title.setObjectName("appLoadingPopupTitle")
        layout.addWidget(self._title)

        self._message = QLabel("", self)
        self._message.setObjectName("appLoadingPopupMessage")
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

    def show_message(self, title: str, message: str) -> None:
        self._title.setText(title)
        self._message.setText(message)
        self.adjustSize()

        parent = self.parentWidget()
        if parent is not None:
            x_pos = max(12, (parent.width() - self.width()) // 2)
            y_pos = max(12, (parent.height() - self.height()) // 2)
            self.move(x_pos, y_pos)

        self.show()
        self.raise_()
