# -*- coding: utf-8 -*-
"""程序编辑工作区通用编辑器。"""
from __future__ import annotations

import copy
import re

from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..omron_symbol_types import normalize_data_type
from ..program_models import LadderCell, LadderElement, LadderNetwork, ProgramUnit, VariableDecl
from ..program_symbols import ProgramSymbolIndex, SuggestionItem, ST_KEYWORDS
from .data_type_delegate import DataTypeDelegate


_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


class _UnknownTokenHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:  # noqa: ANN001
        super().__init__(document)
        self._unknowns: set[str] = set()
        self._keyword_format = QTextCharFormat()
        self._keyword_format.setForeground(QColor("#244C7B"))
        self._keyword_format.setFontWeight(QFont.Weight.Bold)
        self._unknown_format = QTextCharFormat()
        self._unknown_format.setUnderlineColor(QColor("#C0392B"))
        self._unknown_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)

    def set_unknowns(self, unknowns: list[str]) -> None:
        self._unknowns = {item.casefold() for item in unknowns}
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for match in _IDENTIFIER_RE.finditer(text):
            token = match.group(0)
            start = match.start()
            length = len(token)
            if token.upper() in ST_KEYWORDS:
                self.setFormat(start, length, self._keyword_format)
            elif token.casefold() in self._unknowns:
                self.setFormat(start, length, self._unknown_format)


class _VariableSnapshotCommand(QUndoCommand):
    def __init__(
        self,
        editor: "FunctionBlockVariableEditor",
        before: list[VariableDecl],
        after: list[VariableDecl],
        text: str,
    ) -> None:
        super().__init__(text)
        self._editor = editor
        self._before = copy.deepcopy(before)
        self._after = copy.deepcopy(after)

    def undo(self) -> None:
        self._editor._apply_variables(self._before)

    def redo(self) -> None:
        self._editor._apply_variables(self._after)


class FunctionBlockVariableEditor(QWidget):
    modified = Signal()

    COL_CATEGORY = 0
    COL_NAME = 1
    COL_DTYPE = 2
    COL_COMMENT = 3
    COL_INITIAL = 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._variables: list[VariableDecl] = []
        self._undo_stack = QUndoStack(self)
        self._applying = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QLabel("FB 变量定义")
        header.setStyleSheet("font-weight: 700; color: #244C7B;")
        root.addWidget(header)

        button_row = QWidget(self)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        add_button = QPushButton("添加变量", button_row)
        duplicate_button = QPushButton("复制选中", button_row)
        delete_button = QPushButton("删除选中", button_row)
        add_button.clicked.connect(lambda: self.add_variable())
        duplicate_button.clicked.connect(self.duplicate_selected_rows)
        delete_button.clicked.connect(self.delete_selected_rows)
        for button in (add_button, duplicate_button, delete_button):
            button.setProperty("compact", "true")
            button_layout.addWidget(button, 0)
        button_layout.addStretch(1)
        root.addWidget(button_row, 0)

        self._table = QTableWidget(0, 5, self)
        self._table.setHorizontalHeaderLabels(["类别", "名称", "数据类型", "注释", "初始值"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setItemDelegateForColumn(self.COL_DTYPE, DataTypeDelegate(self._table))
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, 1)

    def set_variables(self, variables: list[VariableDecl]) -> None:
        self._variables = copy.deepcopy(variables)
        self._rebuild_table()

    def variables(self) -> list[VariableDecl]:
        return copy.deepcopy(self._variables)

    def validation_messages(self) -> list[str]:
        seen: set[str] = set()
        issues: list[str] = []
        for variable in self._variables:
            name = variable.name.strip()
            if not name:
                issues.append("变量名称不能为空")
                continue
            folded = name.casefold()
            if folded in seen:
                issues.append(f"变量名称重复：{name}")
            seen.add(folded)
        return issues

    def update_cell(self, row: int, column: int, text: str) -> None:
        if row < 0 or row >= len(self._variables):
            return
        before = self.variables()
        after = self.variables()
        variable = after[row]
        value = text.strip()
        if column == self.COL_CATEGORY:
            variable.category = value or variable.category
        elif column == self.COL_NAME:
            variable.name = value
        elif column == self.COL_DTYPE:
            variable.data_type = normalize_data_type(value or "BOOL")
        elif column == self.COL_COMMENT:
            variable.comment = value
        elif column == self.COL_INITIAL:
            variable.initial_value = value
        if before == after:
            return
        self._undo_stack.push(_VariableSnapshotCommand(self, before, after, "编辑 FB 变量"))

    def add_variable(self, *, category: str = "VAR") -> None:
        before = self.variables()
        after = self.variables()
        after.append(VariableDecl(name="", data_type="BOOL", category=category))
        self._undo_stack.push(_VariableSnapshotCommand(self, before, after, "添加 FB 变量"))

    def duplicate_selected_rows(self) -> None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()})
        if not rows:
            return
        before = self.variables()
        after = self.variables()
        inserts = [copy.deepcopy(after[row]) for row in rows if 0 <= row < len(after)]
        for offset, variable in enumerate(inserts):
            after.insert(rows[-1] + 1 + offset, variable)
        self._undo_stack.push(_VariableSnapshotCommand(self, before, after, "复制 FB 变量"))

    def delete_selected_rows(self) -> None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        before = self.variables()
        after = self.variables()
        for row in rows:
            if 0 <= row < len(after):
                after.pop(row)
        self._undo_stack.push(_VariableSnapshotCommand(self, before, after, "删除 FB 变量"))

    def undo(self) -> None:
        self._undo_stack.undo()

    def redo(self) -> None:
        self._undo_stack.redo()

    def _apply_variables(self, variables: list[VariableDecl]) -> None:
        self._variables = copy.deepcopy(variables)
        self._rebuild_table()
        self.modified.emit()

    def _rebuild_table(self) -> None:
        self._applying = True
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._variables))
        for row, variable in enumerate(self._variables):
            values = [
                variable.category,
                variable.name,
                variable.data_type,
                variable.comment,
                variable.initial_value,
            ]
            for column, value in enumerate(values):
                item = self._table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self._table.setItem(row, column, item)
                item.setText(value)
        self._table.blockSignals(False)
        self._applying = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._applying:
            return
        self.update_cell(item.row(), item.column(), item.text())


class StructuredTextEditor(QWidget):
    modified = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._symbol_index: ProgramSymbolIndex | None = None
        self._function_block = None
        self._program_unit: ProgramUnit | None = None
        self._unknowns: list[str] = []
        self._refreshing_unknowns = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        hint = QLabel("ST 结构化文本")
        hint.setStyleSheet("font-weight: 700; color: #244C7B;")
        self._create_symbol_btn = QPushButton("创建当前变量", header)
        self._create_symbol_btn.setProperty("compact", "true")
        self._create_symbol_btn.clicked.connect(self.create_current_symbol)
        header_layout.addWidget(hint, 0)
        header_layout.addStretch(1)
        header_layout.addWidget(self._create_symbol_btn, 0)
        root.addWidget(header, 0)

        self._editor = QPlainTextEdit(self)
        self._editor.setPlaceholderText("输入 ST 程序；Ctrl+Space 触发变量提示。")
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.cursorPositionChanged.connect(self._on_cursor_position_changed)
        root.addWidget(self._editor, 1)

        self._completion_list = QListWidget(self)
        self._completion_list.setMaximumHeight(132)
        self._completion_list.hide()
        self._completion_list.itemActivated.connect(lambda item: self.insert_completion(item.text()))
        root.addWidget(self._completion_list, 0)

        self._highlighter = _UnknownTokenHighlighter(self._editor.document())
        self._completion_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self._editor)
        self._completion_shortcut.activated.connect(self.show_completion_panel)
        self._refresh_current_line_highlight()

    def set_symbol_index(
        self,
        symbol_index: ProgramSymbolIndex,
        *,
        function_block=None,
        program_unit: ProgramUnit | None = None,
    ) -> None:
        self._symbol_index = symbol_index
        self._function_block = function_block
        self._program_unit = program_unit
        self._refresh_unknowns()

    def set_source(self, source: str) -> None:
        self._editor.setPlainText(source)
        self._refresh_unknowns()

    def source(self) -> str:
        return self._editor.toPlainText()

    def completion_items(self, prefix: str) -> list[SuggestionItem]:
        if self._symbol_index is None:
            return []
        return self._symbol_index.suggestions(
            prefix,
            mode="st",
            function_block=self._function_block,
            program_unit=self._program_unit,
        )

    def unknown_identifiers(self) -> list[str]:
        return list(self._unknowns)

    def suggestion_texts(self) -> list[str]:
        return [self._completion_list.item(index).text() for index in range(self._completion_list.count())]

    def show_completion_panel(self, prefix: str | None = None) -> None:
        token = prefix if prefix is not None else self._current_prefix()
        items = self.completion_items(token)
        self._completion_list.clear()
        for item in items:
            self._completion_list.addItem(f"{item.text}")
        self._completion_list.setVisible(bool(items))
        if items:
            self._completion_list.setCurrentRow(0)

    def insert_completion(self, value: str) -> None:
        cursor = self._editor.textCursor()
        token = self._current_prefix()
        for _ in range(len(token)):
            cursor.deletePreviousChar()
        cursor.insertText(value)
        self._editor.setTextCursor(cursor)
        self._completion_list.hide()

    def create_missing_symbol(self, name: str, *, target: str) -> None:
        if self._symbol_index is None:
            return
        self._symbol_index.create_missing_symbol(name, target=target, function_block=self._function_block)
        self._refresh_unknowns()
        self.modified.emit()

    def create_current_symbol(self) -> None:
        token = self._current_prefix()
        if not token:
            return
        target = "function_block" if self._function_block is not None else "io"
        self.create_missing_symbol(token, target=target)

    def _on_text_changed(self) -> None:
        self._refresh_unknowns()
        self._refresh_current_line_highlight()
        self._update_completion_visibility()
        self.modified.emit()

    def _on_cursor_position_changed(self) -> None:
        self._refresh_current_line_highlight()
        self._update_completion_visibility()

    def _refresh_unknowns(self) -> None:
        if self._refreshing_unknowns:
            return
        self._refreshing_unknowns = True
        text = self._editor.toPlainText()
        unknowns: list[str] = []
        seen: set[str] = set()
        known = (
            self._symbol_index.known_names(
                function_block=self._function_block,
                program_unit=self._program_unit,
                mode="st",
            )
            if self._symbol_index is not None
            else set(ST_KEYWORDS)
        )
        known_folded = {item.casefold() for item in known}
        for token in _IDENTIFIER_RE.findall(text):
            if token.casefold() in known_folded or token.isupper():
                continue
            if token.casefold() in seen:
                continue
            seen.add(token.casefold())
            unknowns.append(token)
        self._unknowns = unknowns
        self._highlighter.set_unknowns(unknowns)
        self._refreshing_unknowns = False

    def _current_prefix(self) -> str:
        cursor = self._editor.textCursor()
        block_text = cursor.block().text()
        position = cursor.positionInBlock()
        prefix = []
        index = position - 1
        while index >= 0:
            char = block_text[index]
            if not (char.isalnum() or char == "_"):
                break
            prefix.append(char)
            index -= 1
        return "".join(reversed(prefix))

    def _update_completion_visibility(self) -> None:
        token = self._current_prefix()
        if token:
            self.show_completion_panel(token)
            return
        self._completion_list.hide()

    def _refresh_current_line_highlight(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#EAF3FF"))
        selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selection.cursor = self._editor.textCursor()
        selection.cursor.clearSelection()
        self._editor.setExtraSelections([selection])


class _LadderSnapshotCommand(QUndoCommand):
    def __init__(
        self,
        editor: "LadderEditorWidget",
        before: list[LadderNetwork],
        after: list[LadderNetwork],
        text: str,
    ) -> None:
        super().__init__(text)
        self._editor = editor
        self._before = copy.deepcopy(before)
        self._after = copy.deepcopy(after)

    def undo(self) -> None:
        self._editor._apply_networks(self._before)

    def redo(self) -> None:
        self._editor._apply_networks(self._after)


class LadderEditorWidget(QWidget):
    modified = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._symbol_index: ProgramSymbolIndex | None = None
        self._function_block = None
        self._program_unit: ProgramUnit | None = None
        self._undo_stack = QUndoStack(self)
        self._networks = [LadderNetwork(title="网络 1", rows=6, columns=8)]
        self._applying = False
        self._clipboard_element: LadderElement | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        title = QLabel("梯形图网络编辑")
        title.setStyleSheet("font-weight: 700; color: #244C7B;")
        root.addWidget(title)

        controls = QWidget(self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        self._operand_edit = QLineEdit(controls)
        self._operand_edit.setPlaceholderText("输入变量名或指令操作数")
        self._operand_model = QStringListModel(self)
        self._operand_completer = QCompleter(self._operand_model, self._operand_edit)
        self._operand_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._operand_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._operand_edit.setCompleter(self._operand_completer)
        self._operand_edit.textEdited.connect(self._refresh_operand_completions)
        controls_layout.addWidget(self._operand_edit, 1)
        self._create_operand_btn = QPushButton("创建变量", controls)
        self._create_operand_btn.setProperty("compact", "true")
        self._create_operand_btn.clicked.connect(self.create_operand_symbol)
        controls_layout.addWidget(self._create_operand_btn, 0)
        for label, kind in (
            ("常开", "contact_no"),
            ("常闭", "contact_nc"),
            ("线圈", "coil"),
            ("置位", "set"),
            ("复位", "reset"),
            ("指令块", "box"),
            ("分支", "branch"),
            ("连线", "line"),
        ):
            button = QPushButton(label, controls)
            button.setProperty("compact", "true")
            button.clicked.connect(lambda _checked=False, current_kind=kind: self._place_at_current_cell(current_kind))
            controls_layout.addWidget(button, 0)
        add_network_button = QPushButton("新增网络", controls)
        add_network_button.setProperty("compact", "true")
        add_network_button.clicked.connect(self.add_network)
        controls_layout.addWidget(add_network_button, 0)
        root.addWidget(controls, 0)

        splitter = QSplitter(self)
        self._network_list = QListWidget(splitter)
        self._network_list.currentRowChanged.connect(self._load_current_network)
        self._grid = QTableWidget(splitter)
        self._grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._grid.currentCellChanged.connect(self._sync_operand_from_current_cell)
        splitter.addWidget(self._network_list)
        splitter.addWidget(self._grid)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self._grid)
        self._copy_shortcut.activated.connect(self.copy_current_cell)
        self._paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self._grid)
        self._paste_shortcut.activated.connect(self.paste_current_cell)
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._grid)
        self._delete_shortcut.activated.connect(self.delete_current_cell)

        self._apply_networks(self._networks)

    def set_symbol_index(
        self,
        symbol_index: ProgramSymbolIndex,
        *,
        function_block=None,
        program_unit: ProgramUnit | None = None,
    ) -> None:
        self._symbol_index = symbol_index
        self._function_block = function_block
        self._program_unit = program_unit

    def set_networks(self, networks: list[LadderNetwork]) -> None:
        self._apply_networks(networks or [LadderNetwork(title="网络 1", rows=6, columns=8)])

    def networks(self) -> list[LadderNetwork]:
        return copy.deepcopy(self._networks)

    def completion_items(self, prefix: str) -> list[SuggestionItem]:
        if self._symbol_index is None:
            return []
        return self._symbol_index.suggestions(
            prefix,
            mode="ladder",
            function_block=self._function_block,
            program_unit=self._program_unit,
        )

    def add_network(self) -> None:
        before = self.networks()
        after = self.networks()
        after.append(LadderNetwork(title=f"网络 {len(after) + 1}", rows=6, columns=8))
        self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "新增梯形图网络"))

    def create_missing_symbol(self, name: str, *, target: str | None = None) -> None:
        if self._symbol_index is None:
            return
        resolved_target = target or ("function_block" if self._function_block is not None else "io")
        self._symbol_index.create_missing_symbol(
            name,
            target=resolved_target,
            function_block=self._function_block,
        )
        self._refresh_operand_completions(self._operand_edit.text())
        self.modified.emit()

    def place_element(self, row: int, column: int, kind: str, *, operand: str = "", params: list[str] | None = None) -> None:
        before = self.networks()
        after = self.networks()
        network_index = self._network_list.currentRow()
        network_index = network_index if network_index >= 0 else 0
        while network_index >= len(after):
            after.append(LadderNetwork(title=f"网络 {len(after) + 1}", rows=6, columns=8))
        network = after[network_index]
        element = LadderElement(kind=kind, operand=operand, params=list(params or []))
        cells = [cell for cell in network.cells if not (cell.row == row and cell.column == column)]
        cells.append(LadderCell(row=row, column=column, element=element))
        cells.sort(key=lambda cell: (cell.row, cell.column))
        network.cells = cells
        self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "放置梯形图元件"))

    def delete_current_cell(self, row: int | None = None, column: int | None = None) -> None:
        network_index = self._network_list.currentRow()
        row, column = self._resolve_cell_position(row, column)
        if network_index < 0 or row < 0 or column < 0:
            return
        before = self.networks()
        after = self.networks()
        network = after[network_index]
        remaining = [cell for cell in network.cells if not (cell.row == row and cell.column == column)]
        if len(remaining) == len(network.cells):
            return
        network.cells = remaining
        self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "删除梯形图元件"))

    def copy_current_cell(self, row: int | None = None, column: int | None = None) -> None:
        row, column = self._resolve_cell_position(row, column)
        element = self._element_at(row, column)
        if element is None:
            return
        self._clipboard_element = copy.deepcopy(element)

    def paste_current_cell(self, row: int | None = None, column: int | None = None) -> None:
        if self._clipboard_element is None:
            return
        row, column = self._resolve_cell_position(row, column)
        row = max(0, row)
        column = max(0, column)
        self.place_element(
            row,
            column,
            self._clipboard_element.kind,
            operand=self._clipboard_element.operand,
            params=self._clipboard_element.params,
        )

    def undo(self) -> None:
        self._undo_stack.undo()

    def redo(self) -> None:
        self._undo_stack.redo()

    def _apply_networks(self, networks: list[LadderNetwork]) -> None:
        self._applying = True
        self._networks = copy.deepcopy(networks)
        self._network_list.blockSignals(True)
        self._network_list.clear()
        for index, network in enumerate(self._networks, start=1):
            self._network_list.addItem(network.title or f"网络 {index}")
        self._network_list.blockSignals(False)
        self._network_list.setCurrentRow(0 if self._networks else -1)
        self._load_current_network(0 if self._networks else -1)
        self._applying = False
        self.modified.emit()

    def _load_current_network(self, row: int) -> None:
        if self._applying or row < 0 or row >= len(self._networks):
            return
        network = self._networks[row]
        self._grid.clear()
        self._grid.setRowCount(network.rows)
        self._grid.setColumnCount(network.columns)
        for cell in network.cells:
            item = QTableWidgetItem(self._render_element(cell.element))
            item.setData(Qt.ItemDataRole.UserRole, cell.element.kind if cell.element else "")
            self._grid.setItem(cell.row, cell.column, item)
        self._sync_operand_from_current_cell(self._grid.currentRow(), self._grid.currentColumn(), -1, -1)

    def _render_element(self, element: LadderElement | None) -> str:
        if element is None:
            return ""
        prefix_map = {
            "contact_no": "NO",
            "contact_nc": "NC",
            "coil": "COIL",
            "set": "SET",
            "reset": "RST",
            "box": "BOX",
            "branch": "BR",
            "line": "--",
        }
        prefix = prefix_map.get(element.kind, element.kind.upper())
        params = f" ({', '.join(element.params)})" if element.params else ""
        operand = f" {element.operand}" if element.operand else ""
        return f"{prefix}{operand}{params}"

    def _refresh_operand_completions(self, text: str) -> None:
        self._operand_model.setStringList([item.text for item in self.completion_items(text)])

    def create_operand_symbol(self) -> None:
        operand = self._operand_edit.text().strip()
        if not operand:
            return
        self.create_missing_symbol(operand)

    def _place_at_current_cell(self, kind: str) -> None:
        row = max(0, self._grid.currentRow())
        column = max(0, self._grid.currentColumn())
        self.place_element(row, column, kind, operand=self._operand_edit.text().strip())

    def _current_element(self) -> LadderElement | None:
        row, column = self._resolve_cell_position(None, None)
        return self._element_at(row, column)

    def _element_at(self, row: int, column: int) -> LadderElement | None:
        network_index = self._network_list.currentRow()
        if network_index < 0 or row < 0 or column < 0 or network_index >= len(self._networks):
            return None
        for cell in self._networks[network_index].cells:
            if cell.row == row and cell.column == column:
                return cell.element
        return None

    def _resolve_cell_position(self, row: int | None, column: int | None) -> tuple[int, int]:
        resolved_row = self._grid.currentRow() if row is None else row
        resolved_column = self._grid.currentColumn() if column is None else column
        return resolved_row, resolved_column

    def _sync_operand_from_current_cell(self, current_row: int, current_column: int, _previous_row: int, _previous_column: int) -> None:
        if current_row < 0 or current_column < 0:
            return
        element = self._current_element()
        self._operand_edit.setText(element.operand if element is not None else "")
