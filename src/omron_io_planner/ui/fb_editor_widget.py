# -*- coding: utf-8 -*-
"""功能块：变量表（底部分类 Tab）+ 程序体（ST/梯形图）一体化编辑。"""
from __future__ import annotations

import copy
from typing import Final

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..omron_symbol_types import normalize_data_type
from ..program_models import FunctionBlock, VariableDecl, default_ladder_network_v2
from ..program_symbols import ProgramSymbolIndex
from .data_type_delegate import DataTypeDelegate
from .ladder_editor_widget import LadderEditorWidget
from .program_editors import StructuredTextEditor, variable_table_row_height

# 与 CX 习惯对齐：底部分类（不含「外部」）
_TAB_LABELS: Final[tuple[str, ...]] = ("内部", "输入", "输出", "输入输出")

_TAB_CATEGORIES: Final[tuple[frozenset[str], ...]] = (
    frozenset({"VAR", "VAR_TEMP"}),
    frozenset({"IN"}),
    frozenset({"OUT"}),
    frozenset({"IN_OUT"}),
)

_DEFAULT_CATEGORY_FOR_TAB: Final[tuple[str, ...]] = ("VAR", "IN", "OUT", "IN_OUT")

# 每个分类 Tab 下至少展示的行数，便于直接录入而无需反复点「添加」
_FB_VAR_TABLE_MIN_ROWS: Final[int] = 20


class _FbVarListCommand(QUndoCommand):
    def __init__(
        self,
        editor: "FunctionBlockEditorWidget",
        before: list[VariableDecl],
        after: list[VariableDecl],
        text: str,
    ) -> None:
        super().__init__(text)
        self._editor = editor
        self._before = copy.deepcopy(before)
        self._after = copy.deepcopy(after)

    def undo(self) -> None:
        self._editor._apply_variable_list(self._before)

    def redo(self) -> None:
        self._editor._apply_variable_list(self._after)


# 欧姆龙 / IEC 61131-3 ST 常用骨架（占位便于继续编辑）
# 缩进四空格，与 ST 编辑器一致
_ST_SNIPPETS: Final[tuple[tuple[str, str], ...]] = (
    ("IF", "IF (* 条件 *) THEN\n    \nEND_IF;"),
    ("ELSIF", "ELSIF (* 条件 *) THEN\n    \n"),
    ("ELSE", "ELSE\n    \n"),
    ("CASE", "CASE (* 表达式 *) OF\n    0:\n        ;\nEND_CASE;"),
    ("FOR", "FOR (* i *) := 0 TO 10 BY 1 DO\n    \nEND_FOR;"),
    ("WHILE", "WHILE (* 条件 *) DO\n    \nEND_WHILE;"),
    ("REPEAT", "REPEAT\n    \nUNTIL (* 条件 *) END_REPEAT;"),
    ("赋值", "(* 变量 *) := (* 表达式 *);"),
)


class FunctionBlockEditorWidget(QWidget):
    """上：变量表 + 底部分类 Tab；下：ST 快捷栏 + ST 编辑器，或梯形图编辑器。"""

    modified = Signal()

    COL_NAME = 0
    COL_DTYPE = 1
    COL_AT = 2
    COL_INIT = 3
    COL_COMMENT = 4
    COL_RETAIN = 5

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._block: FunctionBlock | None = None
        self._symbol_index: ProgramSymbolIndex | None = None
        self._undo_stack = QUndoStack(self)
        self._applying = False
        self._tab_index = 0
        self._row_to_global: list[int] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._title = QLabel("", self)
        self._title.setStyleSheet("font-weight: 700; color: #244C7B;")
        root.addWidget(self._title)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setObjectName("fbEditorVerticalSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        top = QWidget(splitter)
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        btn_row = QWidget(top)
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)
        self._btn_add_var = QPushButton("添加", btn_row)
        self._btn_add_var_temp = QPushButton("添加 VAR_TEMP", btn_row)
        self._btn_dup = QPushButton("复制选中", btn_row)
        self._btn_del = QPushButton("删除选中", btn_row)
        self._btn_add_var.clicked.connect(self._on_add_clicked)
        self._btn_add_var_temp.clicked.connect(lambda: self._add_variable_with_category("VAR_TEMP"))
        self._btn_dup.clicked.connect(self._duplicate_selected)
        self._btn_del.clicked.connect(self._delete_selected)
        for b in (self._btn_add_var, self._btn_add_var_temp, self._btn_dup, self._btn_del):
            b.setProperty("compact", "true")
        btn_layout.addWidget(self._btn_add_var, 0)
        btn_layout.addWidget(self._btn_add_var_temp, 0)
        btn_layout.addWidget(self._btn_dup, 0)
        btn_layout.addWidget(self._btn_del, 0)
        btn_layout.addStretch(1)
        top_layout.addWidget(btn_row, 0)

        self._table = QTableWidget(0, 6, top)
        self._table.setHorizontalHeaderLabels(["名称", "数据类型", "AT", "初始值", "注释", "保留"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setItemDelegateForColumn(self.COL_DTYPE, DataTypeDelegate(self._table))
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.setMinimumHeight(120)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        th = self._table.horizontalHeader()
        th.setStretchLastSection(True)
        th.setSectionResizeMode(self.COL_RETAIN, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setDefaultSectionSize(variable_table_row_height(self._table))
        top_layout.addWidget(self._table, 1)

        self._tab_bar = QTabBar(top)
        for label in _TAB_LABELS:
            self._tab_bar.addTab(label)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        top_layout.addWidget(self._tab_bar, 0)

        bottom = QWidget(splitter)
        bottom.setMinimumHeight(160)
        self._bottom_layout = QVBoxLayout(bottom)
        self._bottom_layout.setContentsMargins(0, 0, 0, 0)
        self._bottom_layout.setSpacing(6)

        self._st_snippet_host = QWidget(bottom)
        snippet_layout = QHBoxLayout(self._st_snippet_host)
        snippet_layout.setContentsMargins(0, 0, 0, 0)
        snippet_layout.setSpacing(4)
        snippet_label = QLabel("ST 快捷插入：", self._st_snippet_host)
        snippet_label.setStyleSheet("color: #5c6578;")
        snippet_layout.addWidget(snippet_label, 0)
        scroll = QScrollArea(self._st_snippet_host)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(40)
        inner = QWidget()
        inner_row = QHBoxLayout(inner)
        inner_row.setContentsMargins(0, 0, 0, 0)
        inner_row.setSpacing(4)
        for label, text in _ST_SNIPPETS:
            b = QPushButton(label, inner)
            b.setProperty("compact", "true")
            b.clicked.connect(lambda _c=False, t=text: self._insert_st_snippet(t))
            inner_row.addWidget(b, 0)
        self._btn_st_comment = QPushButton("注释 (*)", inner)
        self._btn_st_comment.setProperty("compact", "true")
        self._btn_st_comment.setToolTip("插入或包围 IEC 行注释 (* … *)")
        self._btn_st_comment.clicked.connect(self._on_st_comment_snippet)
        inner_row.addWidget(self._btn_st_comment, 0)
        inner_row.addStretch(1)
        scroll.setWidget(inner)
        snippet_layout.addWidget(scroll, 1)
        self._st_snippet_host.hide()

        self._st_editor = StructuredTextEditor(bottom, show_comment_button=False)
        self._ladder_editor = LadderEditorWidget(bottom)
        self._bottom_layout.addWidget(self._st_snippet_host, 0)
        self._bottom_layout.addWidget(self._st_editor, 1)
        self._bottom_layout.addWidget(self._ladder_editor, 1)
        self._ladder_editor.hide()

        self._st_editor.modified.connect(self.modified.emit)
        self._ladder_editor.modified.connect(self.modified.emit)

        top.setMinimumHeight(140)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([260, 400])
        root.addWidget(splitter, 1)

        self._refresh_add_buttons_visibility()

    def set_symbol_index(self, symbol_index: ProgramSymbolIndex) -> None:
        self._symbol_index = symbol_index

    def set_function_block(self, block: FunctionBlock | None) -> None:
        self._undo_stack.clear()
        self._block = block
        if block is None:
            self._title.setText("")
            return
        self._title.setText(f"{block.name} — 变量与程序体")
        self._tab_index = max(0, min(self._tab_bar.currentIndex(), self._tab_bar.count() - 1))
        self._refresh_body_editors()
        self._rebuild_filtered_table()
        self._refresh_add_buttons_visibility()

    def flush_to_block(self) -> None:
        if self._block is None:
            return
        if self._block.implementation_language == "st":
            self._block.st_document.source = self._st_editor.source()
        else:
            self._block.ladder_networks = self._ladder_editor.networks()

    def _refresh_body_editors(self) -> None:
        if self._block is None or self._symbol_index is None:
            return
        if self._block.implementation_language == "st":
            self._st_snippet_host.show()
            self._st_editor.show()
            self._ladder_editor.hide()
            self._st_editor.set_symbol_index(self._symbol_index, function_block=self._block)
            self._st_editor.set_source(self._block.st_document.source)
        else:
            self._st_snippet_host.hide()
            self._st_editor.hide()
            self._ladder_editor.show()
            self._ladder_editor.set_symbol_index(self._symbol_index, function_block=self._block)
            nets = self._block.ladder_networks
            self._ladder_editor.set_networks(nets or [default_ladder_network_v2(title="网络 1", n_rungs=6)])

    def _insert_st_snippet(self, text: str) -> None:
        self._st_editor.insert_snippet(text)

    def _on_st_comment_snippet(self) -> None:
        self._st_editor.insert_comment_snippet()

    def _on_tab_changed(self, index: int) -> None:
        self._tab_index = index
        self._refresh_add_buttons_visibility()
        self._rebuild_filtered_table()

    def _refresh_add_buttons_visibility(self) -> None:
        internal = self._tab_index == 0
        self._btn_add_var_temp.setVisible(internal)
        self._btn_add_var.setText("添加 VAR" if internal else "添加")

    def _categories_for_current_tab(self) -> frozenset[str]:
        return _TAB_CATEGORIES[self._tab_index]

    def _default_category_for_add(self) -> str:
        return _DEFAULT_CATEGORY_FOR_TAB[self._tab_index]

    def _on_add_clicked(self) -> None:
        self._add_variable_with_category(self._default_category_for_add())

    def _add_variable_with_category(self, category: str) -> None:
        if self._block is None:
            return
        before = copy.deepcopy(self._block.variables)
        after = copy.deepcopy(self._block.variables)
        after.append(VariableDecl(name="", data_type="BOOL", category=category))
        self._undo_stack.push(_FbVarListCommand(self, before, after, "添加 FB 变量"))

    def _duplicate_selected(self) -> None:
        if self._block is None:
            return
        rows = sorted({i.row() for i in self._table.selectedIndexes()})
        if not rows:
            return
        gidxs = [self._row_to_global[r] for r in rows if 0 <= r < len(self._row_to_global)]
        if not gidxs:
            return
        before = copy.deepcopy(self._block.variables)
        after = copy.deepcopy(self._block.variables)
        inserts = [copy.deepcopy(after[i]) for i in gidxs if 0 <= i < len(after)]
        insert_at = max(gidxs) + 1
        for offset, decl in enumerate(inserts):
            after.insert(insert_at + offset, decl)
        self._undo_stack.push(_FbVarListCommand(self, before, after, "复制 FB 变量"))

    def _delete_selected(self) -> None:
        if self._block is None:
            return
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        gidxs = sorted({self._row_to_global[r] for r in rows if 0 <= r < len(self._row_to_global)}, reverse=True)
        if not gidxs:
            return
        before = copy.deepcopy(self._block.variables)
        after = copy.deepcopy(self._block.variables)
        for gi in gidxs:
            if 0 <= gi < len(after):
                after.pop(gi)
        self._undo_stack.push(_FbVarListCommand(self, before, after, "删除 FB 变量"))

    def _apply_variable_list(self, variables: list[VariableDecl]) -> None:
        if self._block is None:
            return
        self._block.variables = copy.deepcopy(variables)
        self._rebuild_filtered_table()
        self.modified.emit()

    def _global_indices_for_tab(self) -> list[int]:
        if self._block is None:
            return []
        cats = self._categories_for_current_tab()
        return [i for i, v in enumerate(self._block.variables) if v.category in cats]

    def _rebuild_filtered_table(self) -> None:
        if self._block is None:
            self._table.setRowCount(0)
            self._row_to_global = []
            return
        cat = self._default_category_for_add()
        idx_list = self._global_indices_for_tab()
        while len(idx_list) < _FB_VAR_TABLE_MIN_ROWS:
            self._block.variables.append(VariableDecl(name="", data_type="BOOL", category=cat))
            idx_list = self._global_indices_for_tab()
        self._applying = True
        self._table.blockSignals(True)
        self._row_to_global = self._global_indices_for_tab()
        self._table.setRowCount(len(self._row_to_global))
        for row, gidx in enumerate(self._row_to_global):
            var = self._block.variables[gidx]
            texts = [
                var.name,
                var.data_type,
                var.at_address,
                var.initial_value,
                var.comment,
                "",
            ]
            for col, txt in enumerate(texts):
                if col == self.COL_RETAIN:
                    it = QTableWidgetItem()
                    it.setFlags(
                        it.flags()
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable,
                    )
                    it.setCheckState(Qt.CheckState.Checked if var.retain else Qt.CheckState.Unchecked)
                    self._table.setItem(row, col, it)
                else:
                    it = self._table.item(row, col)
                    if it is None:
                        it = QTableWidgetItem()
                        self._table.setItem(row, col, it)
                    it.setText(txt)
        rh = variable_table_row_height(self._table)
        for row in range(self._table.rowCount()):
            self._table.setRowHeight(row, rh)
        self._table.blockSignals(False)
        self._applying = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._applying or self._block is None:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._row_to_global):
            return
        gidx = self._row_to_global[row]
        if gidx < 0 or gidx >= len(self._block.variables):
            return
        before = copy.deepcopy(self._block.variables)
        after = copy.deepcopy(self._block.variables)
        var = after[gidx]
        if col == self.COL_RETAIN:
            var.retain = item.checkState() == Qt.CheckState.Checked
        else:
            val = item.text().strip()
            if col == self.COL_NAME:
                var.name = val
            elif col == self.COL_DTYPE:
                var.data_type = normalize_data_type(val or "BOOL")
            elif col == self.COL_AT:
                var.at_address = val
            elif col == self.COL_INIT:
                var.initial_value = val
            elif col == self.COL_COMMENT:
                var.comment = val
        if before == after:
            return
        self._undo_stack.push(_FbVarListCommand(self, before, after, "编辑 FB 变量"))
        QTimer.singleShot(0, lambda r=row, c=col: self._go_next_table_cell(r, c))

    def _go_next_table_cell(self, prev_row: int, prev_col: int) -> None:
        """提交单元格后跳到下一行同一列。"""
        if self._block is None or self._applying:
            return
        nrows = self._table.rowCount()
        nrow, ncol = prev_row + 1, prev_col
        if nrow < 0 or nrow >= nrows:
            return
        it = self._table.item(nrow, ncol)
        if it is None:
            return
        self._table.setFocus()
        self._table.setCurrentCell(nrow, ncol)
        if ncol != self.COL_RETAIN:
            self._table.editItem(it)
