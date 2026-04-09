# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
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
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
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


class FindReplaceDialog(AppDialog):
    find_next_requested = Signal()
    replace_requested = Signal()
    replace_all_requested = Signal()
    search_options_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("查找和替换", object_name="appFindReplaceDialog", parent=parent)
        self.setModal(False)
        self.setMinimumWidth(460)
        self._replace_mode = False

        intro = QLabel("范围：当前分区编辑表格（当前可见行）。", self._body)
        intro.setWordWrap(True)
        self._body_layout.addWidget(intro)

        fields = QWidget(self._body)
        form = QFormLayout(fields)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._find_edit = QLineEdit(fields)
        self._find_edit.setClearButtonEnabled(True)
        self._find_label = QLabel("查找内容", fields)
        form.addRow(self._find_label, self._find_edit)

        self._replace_edit = QLineEdit(fields)
        self._replace_edit.setClearButtonEnabled(True)
        self._replace_label = QLabel("替换为", fields)
        form.addRow(self._replace_label, self._replace_edit)

        self._case_sensitive = QCheckBox("区分大小写", fields)
        form.addRow(self._case_sensitive)
        self._direction = QComboBox(fields)
        self._direction.addItem("向下", "forward")
        self._direction.addItem("向上", "backward")
        form.addRow("查找方向", self._direction)

        scope_row = QWidget(fields)
        scope_layout = QHBoxLayout(scope_row)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.setSpacing(10)
        self._current_column_only = QCheckBox("仅当前列", scope_row)
        self._selected_only = QCheckBox("仅选区", scope_row)
        scope_layout.addWidget(self._current_column_only, 0)
        scope_layout.addWidget(self._selected_only, 0)
        scope_layout.addStretch(1)
        form.addRow("查找范围", scope_row)
        self._body_layout.addWidget(fields)

        self._status_label = QLabel("", self._body)
        self._status_label.setObjectName("findReplaceStatusLabel")
        self._status_label.setWordWrap(True)
        self._body_layout.addWidget(self._status_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._find_next_btn = QPushButton("查找下一个", self._body)
        self._replace_btn = QPushButton("替换", self._body)
        self._replace_all_btn = QPushButton("全部替换", self._body)
        self._close_btn = QPushButton("关闭", self._body)
        for button in (self._find_next_btn, self._replace_btn, self._replace_all_btn, self._close_btn):
            button_row.addWidget(button)
        self._body_layout.addLayout(button_row)

        self._find_edit.returnPressed.connect(lambda: self.find_next_requested.emit())
        self._replace_edit.returnPressed.connect(lambda: self.replace_requested.emit())
        self._find_edit.textChanged.connect(lambda _text: self.search_options_changed.emit())
        self._case_sensitive.toggled.connect(lambda _checked: self.search_options_changed.emit())
        self._direction.currentIndexChanged.connect(lambda _index: self.search_options_changed.emit())
        self._current_column_only.toggled.connect(lambda _checked: self.search_options_changed.emit())
        self._selected_only.toggled.connect(lambda _checked: self.search_options_changed.emit())
        self._find_next_btn.clicked.connect(lambda _checked=False: self.find_next_requested.emit())
        self._replace_btn.clicked.connect(lambda _checked=False: self.replace_requested.emit())
        self._replace_all_btn.clicked.connect(lambda _checked=False: self.replace_all_requested.emit())
        self._close_btn.clicked.connect(self.hide)

        self.set_replace_mode(False)

    def set_replace_mode(self, enabled: bool) -> None:
        self._replace_mode = bool(enabled)
        self._replace_label.setHidden(not self._replace_mode)
        self._replace_edit.setHidden(not self._replace_mode)
        self._replace_btn.setHidden(not self._replace_mode)
        self._replace_all_btn.setHidden(not self._replace_mode)

    def is_replace_mode(self) -> bool:
        return self._replace_mode

    def search_text(self) -> str:
        return self._find_edit.text()

    def set_search_text(self, text: str) -> None:
        self._find_edit.setText(text)

    def replace_text(self) -> str:
        return self._replace_edit.text()

    def set_replace_text(self, text: str) -> None:
        self._replace_edit.setText(text)

    def case_sensitive(self) -> bool:
        return self._case_sensitive.isChecked()

    def search_direction(self) -> str:
        return str(self._direction.currentData() or "forward")

    def set_search_direction(self, direction: str) -> None:
        target = str(direction or "forward")
        index = self._direction.findData(target)
        self._direction.setCurrentIndex(index if index >= 0 else 0)

    def current_column_only(self) -> bool:
        return self._current_column_only.isChecked()

    def set_current_column_only(self, enabled: bool) -> None:
        self._current_column_only.setChecked(bool(enabled))

    def selected_only(self) -> bool:
        return self._selected_only.isChecked()

    def set_selected_only(self, enabled: bool) -> None:
        self._selected_only.setChecked(bool(enabled))

    def set_status_text(self, text: str) -> None:
        self._status_label.setText(text)

    def focus_search_input(self) -> None:
        self._find_edit.setFocus()
        self._find_edit.selectAll()

    def reject(self) -> None:
        self.hide()


class PreferencesDialog(AppDialog):
    def __init__(
        self,
        *,
        autosave_enabled: bool,
        autosave_interval: int,
        recent_limit: int,
        show_recent_full_path: bool,
        startup_preferences: dict[str, object] | None = None,
        editor_defaults: dict[str, object] | None = None,
        recent_workspace_preferences: dict[str, object] | None = None,
        parent=None,
    ) -> None:
        super().__init__("软件偏好设置", object_name="appPreferencesDialog", parent=parent)
        self.setMinimumWidth(560)
        startup_preferences = dict(startup_preferences or {})
        editor_defaults = dict(editor_defaults or {})
        recent_workspace_preferences = dict(recent_workspace_preferences or {})

        intro = QLabel("配置启动行为、编辑默认值和最近项目工作台。", self._body)
        intro.setWordWrap(True)
        self._body_layout.addWidget(intro)

        tabs = QTabWidget(self._body)
        self._body_layout.addWidget(tabs)

        startup_page = QWidget(tabs)
        startup_layout = QVBoxLayout(startup_page)
        startup_layout.setContentsMargins(0, 0, 0, 0)
        startup_layout.setSpacing(12)

        autosave_group = QGroupBox("自动保存", startup_page)
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
        startup_layout.addWidget(autosave_group)

        startup_group = QGroupBox("启动与窗口", startup_page)
        startup_form = QFormLayout(startup_group)
        startup_form.setHorizontalSpacing(12)
        startup_form.setVerticalSpacing(8)
        self._remember_window_state = QCheckBox("记住上次窗口大小和位置", startup_group)
        self._remember_window_state.setChecked(bool(startup_preferences.get("remember_window_state", False)))
        self._auto_open_recent = QCheckBox("启动时自动打开最近项目", startup_group)
        self._auto_open_recent.setChecked(bool(startup_preferences.get("auto_open_recent", False)))
        self._show_recent_sidebar = QCheckBox("默认显示最近项目栏", startup_group)
        self._show_recent_sidebar.setChecked(bool(startup_preferences.get("show_recent_sidebar", True)))
        startup_form.addRow(self._remember_window_state)
        startup_form.addRow(self._auto_open_recent)
        startup_form.addRow(self._show_recent_sidebar)
        startup_layout.addWidget(startup_group)
        startup_layout.addStretch(1)
        tabs.addTab(startup_page, "启动与窗口")

        editor_page = QWidget(tabs)
        editor_layout = QVBoxLayout(editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(12)

        entry_group = QGroupBox("编辑默认值", editor_page)
        entry_form = QFormLayout(entry_group)
        entry_form.setHorizontalSpacing(12)
        entry_form.setVerticalSpacing(8)
        self._continuous_entry = QCheckBox("启用连续录入模式", entry_group)
        self._continuous_entry.setChecked(bool(editor_defaults.get("continuous_entry", True)))
        self._default_immersive = QCheckBox("新项目默认进入沉浸模式", entry_group)
        self._default_immersive.setChecked(bool(editor_defaults.get("default_immersive", False)))
        self._auto_increment_address = QCheckBox("新行自动续增地址", entry_group)
        self._auto_increment_address.setChecked(bool(editor_defaults.get("auto_increment_address", True)))
        self._inherit_data_type = QCheckBox("继承上行数据类型", entry_group)
        self._inherit_data_type.setChecked(bool(editor_defaults.get("inherit_data_type", True)))
        self._inherit_rack = QCheckBox("继承上行机架位置", entry_group)
        self._inherit_rack.setChecked(bool(editor_defaults.get("inherit_rack", True)))
        self._inherit_usage = QCheckBox("继承上行使用字段", entry_group)
        self._inherit_usage.setChecked(bool(editor_defaults.get("inherit_usage", True)))
        self._auto_increment_name = QCheckBox("名称自动续号", entry_group)
        self._auto_increment_name.setChecked(bool(editor_defaults.get("auto_increment_name", True)))
        self._auto_increment_comment = QCheckBox("注释自动续号 / 配对续写", entry_group)
        self._auto_increment_comment.setChecked(bool(editor_defaults.get("auto_increment_comment", True)))
        self._suggestions_enabled = QCheckBox("启用智能提示列表", entry_group)
        self._suggestions_enabled.setChecked(bool(editor_defaults.get("suggestions_enabled", True)))
        self._suggestion_limit = QSpinBox(entry_group)
        self._suggestion_limit.setRange(3, 20)
        self._suggestion_limit.setValue(int(editor_defaults.get("suggestion_limit", 8) or 8))
        self._row_height = QSpinBox(entry_group)
        self._row_height.setRange(24, 48)
        self._row_height.setValue(int(editor_defaults.get("row_height", 34) or 34))
        self._enter_navigation = QComboBox(entry_group)
        self._enter_navigation.addItems(["down", "right"])
        self._enter_navigation.setCurrentText(str(editor_defaults.get("enter_navigation", "down")))
        self._tab_navigation = QComboBox(entry_group)
        self._tab_navigation.addItems(["right", "down"])
        self._tab_navigation.setCurrentText(str(editor_defaults.get("tab_navigation", "right")))
        entry_form.addRow(self._continuous_entry)
        entry_form.addRow(self._default_immersive)
        entry_form.addRow(self._auto_increment_address)
        entry_form.addRow(self._inherit_data_type)
        entry_form.addRow(self._inherit_rack)
        entry_form.addRow(self._inherit_usage)
        entry_form.addRow(self._auto_increment_name)
        entry_form.addRow(self._auto_increment_comment)
        entry_form.addRow(self._suggestions_enabled)
        entry_form.addRow("提示数量", self._suggestion_limit)
        entry_form.addRow("默认行高", self._row_height)
        entry_form.addRow("Enter 导航", self._enter_navigation)
        entry_form.addRow("Tab 导航", self._tab_navigation)
        editor_layout.addWidget(entry_group)
        editor_layout.addStretch(1)
        tabs.addTab(editor_page, "编辑默认值")

        recent_page = QWidget(tabs)
        recent_layout = QVBoxLayout(recent_page)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(12)

        recent_group = QGroupBox("最近项目工作台", recent_page)
        recent_form = QFormLayout(recent_group)
        recent_form.setHorizontalSpacing(12)
        recent_form.setVerticalSpacing(8)
        self._recent_limit = QSpinBox(recent_group)
        self._recent_limit.setRange(1, 30)
        self._recent_limit.setValue(recent_limit)
        self._show_recent_full_path = QCheckBox("显示完整路径", recent_group)
        self._show_recent_full_path.setChecked(show_recent_full_path)
        self._auto_prune_missing = QCheckBox("启动时自动清理失效项目", recent_group)
        self._auto_prune_missing.setChecked(bool(recent_workspace_preferences.get("auto_prune_missing", True)))
        self._allow_pinned = QCheckBox("允许置顶项目", recent_group)
        self._allow_pinned.setChecked(bool(recent_workspace_preferences.get("allow_pinned", True)))
        recent_form.addRow("最近项目数量", self._recent_limit)
        recent_form.addRow(self._show_recent_full_path)
        recent_form.addRow(self._auto_prune_missing)
        recent_form.addRow(self._allow_pinned)
        recent_layout.addWidget(recent_group)
        recent_layout.addStretch(1)
        tabs.addTab(recent_page, "最近项目")

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
            "startup": {
                "remember_window_state": self._remember_window_state.isChecked(),
                "auto_open_recent": self._auto_open_recent.isChecked(),
                "show_recent_sidebar": self._show_recent_sidebar.isChecked(),
            },
            "editor_defaults": {
                "continuous_entry": self._continuous_entry.isChecked(),
                "default_immersive": self._default_immersive.isChecked(),
                "auto_increment_address": self._auto_increment_address.isChecked(),
                "inherit_data_type": self._inherit_data_type.isChecked(),
                "inherit_rack": self._inherit_rack.isChecked(),
                "inherit_usage": self._inherit_usage.isChecked(),
                "auto_increment_name": self._auto_increment_name.isChecked(),
                "auto_increment_comment": self._auto_increment_comment.isChecked(),
                "suggestions_enabled": self._suggestions_enabled.isChecked(),
                "suggestion_limit": int(self._suggestion_limit.value()),
                "row_height": int(self._row_height.value()),
                "enter_navigation": self._enter_navigation.currentText(),
                "tab_navigation": self._tab_navigation.currentText(),
            },
            "recent_workspace": {
                "auto_prune_missing": self._auto_prune_missing.isChecked(),
                "allow_pinned": self._allow_pinned.isChecked(),
            },
        }


class ProjectSettingsDialog(AppDialog):
    def __init__(
        self,
        *,
        editor_preferences: dict[str, object],
        parent=None,
    ) -> None:
        super().__init__("项目设置", object_name="appProjectSettingsDialog", parent=parent)
        self.setMinimumWidth(560)
        editor_preferences = dict(editor_preferences)
        generation_defaults = dict(editor_preferences.get("generation_defaults") or {})
        phrase_defaults = dict(editor_preferences.get("phrases") or {})

        intro = QLabel("当前项目专属的编辑习惯会覆盖全局默认值。", self._body)
        intro.setWordWrap(True)
        self._body_layout.addWidget(intro)

        self._capture_layout = QCheckBox("使用当前编辑表布局作为项目默认布局", self._body)
        self._capture_layout.setChecked(False)
        self._body_layout.addWidget(self._capture_layout)

        editor_group = QGroupBox("项目级编辑偏好", self._body)
        editor_form = QFormLayout(editor_group)
        editor_form.setHorizontalSpacing(12)
        editor_form.setVerticalSpacing(8)
        self._default_immersive = QCheckBox("当前项目默认进入沉浸模式", editor_group)
        self._default_immersive.setChecked(bool(editor_preferences.get("default_immersive", False)))
        self._suggestions_enabled = QCheckBox("当前项目启用智能提示列表", editor_group)
        self._suggestions_enabled.setChecked(bool(editor_preferences.get("suggestions_enabled", True)))
        self._suggestion_limit = QSpinBox(editor_group)
        self._suggestion_limit.setRange(3, 20)
        self._suggestion_limit.setValue(int(editor_preferences.get("suggestion_limit", 8) or 8))
        editor_form.addRow(self._default_immersive)
        editor_form.addRow(self._suggestions_enabled)
        editor_form.addRow("提示数量", self._suggestion_limit)
        self._body_layout.addWidget(editor_group)

        template_group = QGroupBox("批量生成默认模板", self._body)
        template_form = QFormLayout(template_group)
        template_form.setHorizontalSpacing(12)
        template_form.setVerticalSpacing(8)
        self._start_address = QLineEdit(str(generation_defaults.get("start_address", "")), template_group)
        self._row_count = QSpinBox(template_group)
        self._row_count.setRange(1, 500)
        self._row_count.setValue(int(generation_defaults.get("row_count", 8) or 8))
        self._data_type = QLineEdit(str(generation_defaults.get("data_type", "BOOL")), template_group)
        self._name_template = QLineEdit(str(generation_defaults.get("name_template", "")), template_group)
        self._comment_template = QLineEdit(str(generation_defaults.get("comment_template", "")), template_group)
        self._rack = QLineEdit(str(generation_defaults.get("rack", "")), template_group)
        self._usage = QLineEdit(str(generation_defaults.get("usage", "")), template_group)
        template_form.addRow("起始地址", self._start_address)
        template_form.addRow("生成行数", self._row_count)
        template_form.addRow("数据类型", self._data_type)
        template_form.addRow("名称模板", self._name_template)
        template_form.addRow("注释模板", self._comment_template)
        template_form.addRow("机架位置", self._rack)
        template_form.addRow("使用", self._usage)
        self._body_layout.addWidget(template_group)

        phrase_group = QGroupBox("名称 / 注释短语库", self._body)
        phrase_form = QFormLayout(phrase_group)
        phrase_form.setHorizontalSpacing(12)
        phrase_form.setVerticalSpacing(8)
        self._name_phrases = QPlainTextEdit(phrase_group)
        self._name_phrases.setPlaceholderText("每行一个名称短语")
        self._name_phrases.setPlainText("\n".join(phrase_defaults.get("name", [])))
        self._comment_phrases = QPlainTextEdit(phrase_group)
        self._comment_phrases.setPlaceholderText("每行一个注释短语")
        self._comment_phrases.setPlainText("\n".join(phrase_defaults.get("comment", [])))
        phrase_form.addRow("名称短语", self._name_phrases)
        phrase_form.addRow("注释短语", self._comment_phrases)
        self._body_layout.addWidget(phrase_group)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._body,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._body_layout.addWidget(btns)

    def values(self) -> dict[str, object]:
        return {
            "capture_layout": self._capture_layout.isChecked(),
            "editor": {
                "default_immersive": self._default_immersive.isChecked(),
                "suggestions_enabled": self._suggestions_enabled.isChecked(),
                "suggestion_limit": int(self._suggestion_limit.value()),
            },
            "generation_defaults": {
                "start_address": self._start_address.text().strip(),
                "row_count": int(self._row_count.value()),
                "data_type": self._data_type.text().strip() or "BOOL",
                "name_template": self._name_template.text().strip(),
                "comment_template": self._comment_template.text().strip(),
                "rack": self._rack.text().strip(),
                "usage": self._usage.text().strip(),
            },
            "phrases": {
                "name": [line.strip() for line in self._name_phrases.toPlainText().splitlines() if line.strip()],
                "comment": [line.strip() for line in self._comment_phrases.toPlainText().splitlines() if line.strip()],
            },
        }


class BatchGenerateDialog(AppDialog):
    def __init__(self, *, defaults: dict[str, object], parent=None) -> None:
        super().__init__("批量生成", object_name="appBatchGenerateDialog", parent=parent)
        self.setMinimumWidth(460)
        defaults = dict(defaults)

        intro = QLabel("模板支持 {n} / {n:02} 数字占位，以及 [伸出|缩回] 这类成对选项；会从当前行开始连续写入。", self._body)
        intro.setWordWrap(True)
        self._body_layout.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self._start_address = QLineEdit(str(defaults.get("start_address", "")), self._body)
        self._row_count = QSpinBox(self._body)
        self._row_count.setRange(1, 500)
        self._row_count.setValue(int(defaults.get("row_count", 8) or 8))
        self._data_type = QLineEdit(str(defaults.get("data_type", "BOOL")), self._body)
        self._name_template = QLineEdit(str(defaults.get("name_template", "")), self._body)
        self._comment_template = QLineEdit(str(defaults.get("comment_template", "")), self._body)
        self._rack = QLineEdit(str(defaults.get("rack", "")), self._body)
        self._usage = QLineEdit(str(defaults.get("usage", "")), self._body)
        form.addRow("起始地址", self._start_address)
        form.addRow("生成行数", self._row_count)
        form.addRow("数据类型", self._data_type)
        form.addRow("名称模板", self._name_template)
        form.addRow("注释模板", self._comment_template)
        form.addRow("机架位置", self._rack)
        form.addRow("使用", self._usage)
        self._body_layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._body,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._body_layout.addWidget(btns)

    def values(self) -> dict[str, object]:
        return {
            "start_address": self._start_address.text().strip(),
            "row_count": int(self._row_count.value()),
            "data_type": self._data_type.text().strip() or "BOOL",
            "name_template": self._name_template.text().strip(),
            "comment_template": self._comment_template.text().strip(),
            "rack": self._rack.text().strip(),
            "usage": self._usage.text().strip(),
        }


class BulkRowUpdateDialog(AppDialog):
    def __init__(self, parent=None) -> None:
        super().__init__("批量设置选中行", object_name="appBulkRowUpdateDialog", parent=parent)
        self.setMinimumWidth(420)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self._data_type = QLineEdit(self._body)
        self._rack = QLineEdit(self._body)
        self._usage = QLineEdit(self._body)
        form.addRow("数据类型", self._data_type)
        form.addRow("机架位置", self._rack)
        form.addRow("使用", self._usage)
        self._body_layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self._body,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self._body_layout.addWidget(btns)

    def values(self) -> dict[str, str]:
        return {
            "data_type": self._data_type.text().strip(),
            "rack": self._rack.text().strip(),
            "usage": self._usage.text().strip(),
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
