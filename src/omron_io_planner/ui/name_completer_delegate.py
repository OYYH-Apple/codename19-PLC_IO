# -*- coding: utf-8 -*-
"""
名称/注释列智能补全 Delegate。

当用户编辑时：
1. 基于当前列历史内容生成候选列表
2. 优先给出对立词预测（上→下、伸出→缩回 等）
3. 以输入框下方弹出列表呈现候选
4. 支持方向键、回车和鼠标选择候选
"""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt, QStringListModel
from PySide6.QtWidgets import QCompleter, QLineEdit, QStyledItemDelegate, QStyleOptionViewItem

from .io_table_widget import (
    IoTableWidget,
    _all_names_in_table,
    _cell_background_color,
    _predict_name,
    _prepare_inline_line_edit,
)


class _SuggestionLineEdit(QLineEdit):
    """带下拉候选的 QLineEdit。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._completion_acceptor = None

    def set_completion_acceptor(self, acceptor) -> None:  # noqa: ANN001
        self._completion_acceptor = acceptor

    def _move_popup_selection(self, step: int) -> bool:
        completer = self.completer()
        popup = completer.popup() if completer is not None else None
        model = completer.completionModel() if completer is not None else None
        if popup is None or model is None or model.rowCount() <= 0:
            return False

        current = popup.currentIndex()
        if not current.isValid():
            row = 0 if step >= 0 else model.rowCount() - 1
        else:
            row = max(0, min(current.row() + step, model.rowCount() - 1))

        popup.setCurrentIndex(model.index(row, 0))
        popup.scrollTo(popup.currentIndex())
        return True

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        completer = self.completer()
        popup = completer.popup() if completer is not None else None
        popup_visible = popup is not None and popup.isVisible()
        has_rows = completer is not None and completer.completionModel().rowCount() > 0

        if (
            event.key() == Qt.Key.Key_Down
            and completer is not None
            and has_rows
        ):
            if not popup_visible:
                completer.complete()
            self._move_popup_selection(1)
            return
        if event.key() == Qt.Key.Key_Up and popup_visible:
            if self._move_popup_selection(-1):
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and popup_visible:
            current = popup.currentIndex()
            if current.isValid() and self._completion_acceptor is not None:
                self._completion_acceptor(current.data())
                return
            popup.hide()
        super().keyPressEvent(event)


class NameCompleterDelegate(QStyledItemDelegate):
    """
    名称/注释列 Delegate，支持弹出列表智能补全。
    需要传入对应的 IoTableWidget 以访问现有列内容。
    """

    def __init__(self, table: IoTableWidget, parent=None, source_column: int = IoTableWidget.COL_NAME) -> None:
        super().__init__(parent)
        self._table = table
        self._source_column = source_column

    def createEditor(self, parent, option: QStyleOptionViewItem, index):  # noqa: ANN001
        edit = _SuggestionLineEdit(parent=parent)
        _prepare_inline_line_edit(edit, _cell_background_color(self._table, index.row()))

        model = QStringListModel(edit)
        completer = QCompleter(model, edit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.setWidget(edit)
        popup = completer.popup()
        popup.setAlternatingRowColors(True)
        popup.setMouseTracking(True)
        popup.setStyleSheet(
            "QListView {"
            " background-color: #FFFFFF;"
            " alternate-background-color: #EEF2FF;"
            " border: 1px solid #C8CDD8;"
            " outline: none;"
            " padding: 2px;"
            "}"
            "QListView::item {"
            " padding: 4px 8px;"
            " color: #1E2235;"
            "}"
            "QListView::item:selected {"
            " background-color: #DCE7FF;"
            " color: #1E2235;"
            "}"
        )
        completer.activated[str].connect(lambda value, current=edit: self._apply_completion(current, value))
        edit.set_completion_acceptor(lambda value, current=edit: self._apply_completion(current, value))
        edit.setCompleter(completer)
        edit.textEdited.connect(lambda text, current=edit: self._update_suggestion(current, text))
        return edit

    def _suggestions_for_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        all_names = _all_names_in_table(self._table, self._source_column)
        suggestions: list[str] = []
        seen: set[str] = set()

        predicted = _predict_name(all_names, text)
        if predicted:
            suggestions.append(predicted)
            seen.add(predicted)

        for candidate in reversed(all_names):
            candidate = candidate.strip()
            if (
                not candidate
                or candidate == text
                or candidate in seen
                or not candidate.startswith(text)
            ):
                continue
            suggestions.append(candidate)
            seen.add(candidate)

        return suggestions

    def _update_suggestion(self, edit: QLineEdit, text: str) -> None:
        completer = edit.completer()
        if completer is None:
            return

        suggestions = self._suggestions_for_text(text)
        model = completer.model()
        if isinstance(model, QStringListModel):
            model.setStringList(suggestions)

        popup = completer.popup()
        if suggestions and edit.hasFocus():
            completer.setCompletionPrefix(text)
            completer.complete()
            popup.setCurrentIndex(QModelIndex())
        else:
            popup.hide()

    def _apply_completion(self, edit: QLineEdit, value: str) -> None:
        edit.setText(value)
        edit.setCursorPosition(len(value))
        completer = edit.completer()
        if completer is not None:
            completer.popup().hide()

    def setEditorData(self, editor, index) -> None:  # noqa: ANN001
        if isinstance(editor, QLineEdit):
            val = index.data(Qt.ItemDataRole.DisplayRole)
            editor.setText(str(val) if val else "")

    def setModelData(self, editor, model, index) -> None:  # noqa: ANN001
        if isinstance(editor, QLineEdit):
            self._table.commit_editor_text(index.row(), index.column(), editor.text())
