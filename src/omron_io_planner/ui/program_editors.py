# -*- coding: utf-8 -*-
"""程序编辑工作区通用编辑器。"""
from __future__ import annotations

import copy
import re
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, QSize, QStringListModel, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontInfo,
    QFontMetrics,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..omron_symbol_types import normalize_data_type
from ..st_loose_format import format_st_document, toggle_st_line_comment
from ..program_models import ProgramUnit, VariableDecl, VARIABLE_CATEGORIES
from ..program_symbols import ProgramSymbolIndex, SuggestionItem, ST_KEYWORDS
from .data_type_delegate import DataTypeDelegate
from .ladder_editor_widget import LadderEditorWidget


_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_ST_KEYWORD_UPPER = frozenset(k.upper() for k in ST_KEYWORDS)
_ST_KW_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in ST_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


ST_TAB_SPACES = 4


def variable_table_row_height(widget: QWidget) -> int:
    """变量表行高：略放大，减轻行内编辑占位与文字被裁切。"""
    fm = QFontMetrics(widget.font())
    return max(36, fm.height() + 18)


def _st_line_needs_semicolon_suffix(part: str) -> bool:
    """换行前是否在行尾自动补 ``;``（启发式：THEN/ELSE、注释、标号等不补）。"""
    part = part.rstrip()
    if not part:
        return False
    if part.endswith(";"):
        return False
    if _st_block_comment_depth(part) > 0:
        return False
    if re.fullmatch(r"\s*\(\*.*?\*\)\s*", part, flags=re.DOTALL):
        return False
    if re.search(r":\s*$", part):
        return False
    upper = part.upper().rstrip()
    if upper.endswith(("THEN", "ELSE", "DO")):
        return False
    if re.search(r"\bOF\s*$", upper):
        return False
    simple_open = ("IF", "WHILE", "REPEAT", "FOR", "CASE")
    if upper.strip() in simple_open:
        return False
    return True


def _st_normalize_line_equals_to_colon_equals(part: str) -> str | None:
    """换行时：若可**唯一**确定一处裸 ``=`` 应为赋值，则改为 ``:=``；否则返回 None。

    排除 ``<=`` ``>=`` ``==`` ``!=``、已有 ``:=``、以 IF/… 开头的条件行、字符串与块注释内的 ``=``。
    """
    if ":=" in part:
        return None
    for bad in ("<=", ">=", "!=", "=="):
        if bad in part:
            return None
    if re.match(
        r"^\s*(IF|ELSIF|WHILE|FOR|REPEAT|CASE|UNTIL|NOT|RETURN|EXIT)\b",
        part,
        re.IGNORECASE,
    ):
        return None
    n = len(part)
    i = 0
    depth = 0
    in_str = False
    candidates: list[int] = []
    forbidden_prev = frozenset(":<>!=+-*/%^&|")
    while i < n:
        ch = part[i]
        if in_str:
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            i += 1
            continue
        if depth > 0:
            if i + 1 < n and part[i : i + 2] == "*)":
                depth -= 1
                i += 2
            elif i + 1 < n and part[i : i + 2] == "(*":
                depth += 1
                i += 2
            else:
                i += 1
            continue
        if i + 1 < n and part[i : i + 2] == "(*":
            depth = 1
            i += 2
            continue
        if ch == "=":
            if i == 0:
                i += 1
                continue
            prev = part[i - 1]
            if prev not in forbidden_prev:
                candidates.append(i)
        i += 1
    if len(candidates) != 1:
        return None
    j = candidates[0]
    return part[:j] + ":=" + part[j + 1 :]


class _StSyntaxHighlighter(QSyntaxHighlighter):
    """关键字着色 + 行内注释 + 数字 + 未声明标识下划线（贴近常见 IDE 观感）。"""

    def __init__(self, document) -> None:  # noqa: ANN001
        super().__init__(document)
        self._unknowns: set[str] = set()
        self._kw_format = QTextCharFormat()
        self._kw_format.setForeground(QColor("#0000CC"))
        self._kw_format.setFontWeight(QFont.Weight.Bold)
        self._comment_format = QTextCharFormat()
        self._comment_format.setForeground(QColor("#008000"))
        self._number_format = QTextCharFormat()
        self._number_format.setForeground(QColor("#098658"))
        self._unknown_format = QTextCharFormat()
        self._unknown_format.setUnderlineColor(QColor("#C0392B"))
        self._unknown_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)

    def set_unknowns(self, unknowns: list[str]) -> None:
        self._unknowns = {item.casefold() for item in unknowns}
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for m in re.finditer(r"\(\*.*?\*\)", text):
            self.setFormat(m.start(), m.end() - m.start(), self._comment_format)
        for m in _ST_KW_PATTERN.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._kw_format)
        for m in re.finditer(r"\b\d+(?:\.\d+)?\b", text):
            self.setFormat(m.start(), m.end() - m.start(), self._number_format)
        for match in _IDENTIFIER_RE.finditer(text):
            token = match.group(0)
            start = match.start()
            length = len(token)
            if token.upper() in _ST_KEYWORD_UPPER:
                continue
            if token.casefold() in self._unknowns:
                self.setFormat(start, length, self._unknown_format)


class _StLineNumberArea(QWidget):
    """ST 编辑器左侧行号条（与 QPlainTextEdit 滚动同步）。"""

    def __init__(self, editor: QPlainTextEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._bg = QColor("#f0f2f5")
        self._fg = QColor("#6e7787")
        self.setFixedWidth(self._digits_width())
        editor.blockCountChanged.connect(self._on_block_geometry_changed)
        editor.updateRequest.connect(lambda _rect: self.update())
        editor.verticalScrollBar().valueChanged.connect(lambda _v: self.update())

    def _digits_width(self) -> int:
        n = max(1, self._editor.document().blockCount())
        digits = len(str(n))
        fm = self._editor.fontMetrics()
        return 8 + fm.horizontalAdvance("9") * max(2, digits)

    def _on_block_geometry_changed(self) -> None:
        self.setFixedWidth(self._digits_width())
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._digits_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._bg)
        painter.setPen(self._fg)
        painter.setFont(self._editor.font())
        fm = painter.fontMetrics()
        block = self._editor.firstVisibleBlock()
        block_number = block.blockNumber()
        while block.isValid():
            geo = self._editor.blockBoundingGeometry(block).translated(self._editor.contentOffset())
            top = int(geo.top())
            if not block.isVisible():
                block = block.next()
                block_number += 1
                continue
            if top > self.height():
                break
            if geo.bottom() >= 0:
                painter.drawText(
                    0,
                    top,
                    self.width() - 4,
                    fm.height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                    str(block_number + 1),
                )
            block = block.next()
            block_number += 1


class _StPlainTextEdit(QPlainTextEdit):
    """Tab → 四空格；Shift+Tab 反缩进；Enter 智能换行；可选补全导航与括号配对。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tab_n = ST_TAB_SPACES
        self._completion_nav: Callable[[QKeyEvent], bool] | None = None
        self._auto_pair_enabled = True
        self._toggle_line_comment_cb: Callable[[], None] | None = None
        self._force_completion_cb: Callable[[], None] | None = None

    def set_completion_nav_callback(self, cb: Callable[[QKeyEvent], bool] | None) -> None:
        self._completion_nav = cb

    def set_editor_chord_callbacks(
        self,
        *,
        toggle_line_comment: Callable[[], None] | None = None,
        force_completion: Callable[[], None] | None = None,
    ) -> None:
        """Ctrl+/、Ctrl+Space 等在子控件内优先于 QShortcut 生效（见 keyPressEvent）。"""
        self._toggle_line_comment_cb = toggle_line_comment
        self._force_completion_cb = force_completion

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if self._completion_nav is not None and self._completion_nav(event):
            event.accept()
            return
        if self._try_st_chords(event):
            event.accept()
            return
        if event.key() == Qt.Key.Key_Backspace and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if self._try_backspace_empty_pair():
                event.accept()
                return
        if event.key() == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.textCursor().insertText(" " * self._tab_n)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Backtab or (
            event.key() == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
        ):
            self._unindent_line_start()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self._insert_smart_newline()
            event.accept()
            return
        if self._auto_pair_enabled and self._try_auto_pair(event):
            return
        super().keyPressEvent(event)

    def _try_st_chords(self, event: QKeyEvent) -> bool:
        """在编辑器内直接处理组合键（避免 QShortcut 挂在 QPlainTextEdit 上不触发）。"""
        if event.isAutoRepeat():
            return False
        mask = (
            Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        mods = event.modifiers() & mask
        if mods != Qt.KeyboardModifier.ControlModifier:
            return False
        if event.key() == Qt.Key.Key_Slash:
            if self._toggle_line_comment_cb is not None:
                self._toggle_line_comment_cb()
                return True
            return False
        if event.key() == Qt.Key.Key_Space:
            if self._force_completion_cb is not None:
                self._force_completion_cb()
                return True
            return False
        return False

    def _try_auto_pair(self, event: QKeyEvent) -> bool:
        """`(` `)`、`[` `]`、`'`、`"` 成对插入；`(*` 后的 `(` 不配对。"""
        if not event.text() or len(event.text()) != 1:
            return False
        ch = event.text()
        # 不配单引号，避免注释自然语言中的撇号被拆成一对
        closing = {"(": ")", "[": "]", '"': '"'}
        if ch not in closing:
            return False
        c = self.textCursor()
        if ch == "(":
            pos = c.positionInBlock()
            blk = c.block().text()
            if pos > 0 and blk[pos - 1] == "*":
                return False
        pair = closing[ch]
        c.insertText(ch + pair)
        c.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        self.setTextCursor(c)
        event.accept()
        return True

    def _unindent_line_start(self) -> None:
        c = self.textCursor()
        block = c.block()
        line = block.text()
        if not line:
            return
        remove = 0
        if line[0] == "\t":
            remove = 1
        elif line.startswith(" " * self._tab_n):
            remove = self._tab_n
        else:
            i = 0
            while i < len(line) and line[i] == " " and i < self._tab_n:
                i += 1
            remove = i
        if remove == 0:
            return
        c.beginEditBlock()
        try:
            start = block.position()
            c.setPosition(start)
            c.setPosition(start + remove, QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()
        finally:
            c.endEditBlock()

    def _insert_smart_newline(self) -> None:
        c = self.textCursor()
        block = c.block()
        line = block.text()
        pos = c.positionInBlock()
        doc = self.document()
        abs_pos = block.position() + pos
        plain = doc.toPlainText()
        prefix_for_depth = plain[: abs_pos] if abs_pos <= len(plain) else plain

        if (
            _st_block_comment_depth(prefix_for_depth) == 0
            and not _st_odd_string_quote_before_cursor(doc, abs_pos)
            and line[pos:].strip() == ""
        ):
            c.beginEditBlock()
            try:
                part_raw = line[:pos]
                new_raw = _st_normalize_line_equals_to_colon_equals(part_raw)
                if new_raw is not None and new_raw != part_raw:
                    tc = QTextCursor(block)
                    tc.setPosition(block.position())
                    tc.setPosition(block.position() + pos, QTextCursor.MoveMode.KeepAnchor)
                    tc.removeSelectedText()
                    tc.insertText(new_raw)
                    self.setTextCursor(tc)
                    c = self.textCursor()
                    block = c.block()
                    line = block.text()
                    pos = c.positionInBlock()
                part_r = line[:pos].rstrip()
                if _st_line_needs_semicolon_suffix(part_r):
                    c.insertText(";")
                    block = c.block()
                    line = block.text()
                    pos = c.positionInBlock()
            finally:
                c.endEditBlock()

        before = line[:pos]
        m = re.match(r"^(\s*)", before)
        base = m.group(1) if m else ""
        code = before[len(base) :].rstrip()
        upper = code.upper()
        extra = ""
        if upper.endswith(("THEN", "ELSE", "DO")) or re.search(r"\bOF\s*$", upper):
            extra = " " * self._tab_n
        c.insertText("\n" + base + extra)

    def _try_backspace_empty_pair(self) -> bool:
        """光标夹在空括号/方括号/双引号之间时，一次删除成对符号。"""
        c = self.textCursor()
        if c.hasSelection():
            return False
        pos = c.position()
        doc = self.document()
        if pos <= 0 or pos >= doc.characterCount():
            return False
        prev_ch = self._doc_char_at(doc, pos - 1)
        next_ch = self._doc_char_at(doc, pos)
        if (prev_ch, next_ch) not in {("(", ")"), ("[", "]"), ('"', '"')}:
            return False
        c.setPosition(pos - 1)
        c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        self.setTextCursor(c)
        return True

    @staticmethod
    def _doc_char_at(doc, index: int) -> str:
        if index < 0 or index >= doc.characterCount():
            return ""
        ch = doc.characterAt(index)
        if isinstance(ch, str):
            return ch[:1] if ch else ""
        u = int(ch.unicode())
        return "" if u == 0 else chr(u)


def _st_block_comment_depth(prefix: str) -> int:
    """前缀中未闭合的 ``(* … *)`` 深度（>0 表示光标在块注释内）。"""
    depth = 0
    i = 0
    n = len(prefix)
    while i < n:
        if i + 1 < n and prefix[i : i + 2] == "(*":
            depth += 1
            i += 2
        elif i + 1 < n and prefix[i : i + 2] == "*)":
            depth = max(0, depth - 1)
            i += 2
        else:
            i += 1
    return depth


def _st_odd_string_quote_before_cursor(doc, pos: int) -> bool:
    """当前行内、光标前的双引号是否为奇数个（视为在字符串字面量内）。"""
    blk = doc.findBlock(pos)
    line_start = blk.position()
    if pos < line_start:
        return False
    seg = doc.toPlainText()[line_start:pos]
    return seg.count('"') % 2 == 1


class FbVariableCategoryDelegate(QStyledItemDelegate):
    """FB 变量表「类别」列：限定为 `VARIABLE_CATEGORIES`。"""

    def createEditor(self, parent, option, index):  # noqa: ANN001
        cb = QComboBox(parent)
        cb.addItems(list(VARIABLE_CATEGORIES))
        cb.setFrame(False)
        cb.currentIndexChanged.connect(lambda _i, editor=cb: self._commit_and_close(editor))
        return cb

    def setEditorData(self, editor, index) -> None:  # noqa: ANN001
        if not isinstance(editor, QComboBox):
            return
        raw = index.data(Qt.ItemDataRole.DisplayRole)
        t = (str(raw) if raw is not None else "").strip().upper() or "VAR"
        editor.blockSignals(True)
        try:
            idx = editor.findText(t)
            fb = editor.findText("VAR")
            editor.setCurrentIndex(idx if idx >= 0 else (fb if fb >= 0 else 0))
        finally:
            editor.blockSignals(False)

    def setModelData(self, editor, model, index) -> None:  # noqa: ANN001
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    @staticmethod
    def _commit_and_close(editor: QComboBox) -> None:
        if editor.signalsBlocked():
            return
        parent = editor.parent()
        view = parent if isinstance(parent, QAbstractItemView) else None
        if view is not None:
            view.commitData(editor)
            view.closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)


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

        self._header = QLabel("FB 变量定义")
        self._header.setStyleSheet("font-weight: 700; color: #244C7B;")
        root.addWidget(self._header)

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

        quick_row = QWidget(self)
        quick_layout = QHBoxLayout(quick_row)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.setSpacing(6)
        ql = QLabel("快速添加：", quick_row)
        ql.setStyleSheet("color: #5c6578;")
        quick_layout.addWidget(ql, 0)
        for label, cat in (
            ("IN", "IN"),
            ("OUT", "OUT"),
            ("IN_OUT", "IN_OUT"),
            ("VAR", "VAR"),
            ("VAR_TEMP", "VAR_TEMP"),
        ):
            b = QPushButton(label, quick_row)
            b.setProperty("compact", "true")
            b.clicked.connect(lambda _checked=False, c=cat: self.add_variable(category=c))
            quick_layout.addWidget(b, 0)
        quick_layout.addStretch(1)
        root.addWidget(quick_row, 0)

        self._table = QTableWidget(0, 5, self)
        self._table.setHorizontalHeaderLabels(["类别", "名称", "数据类型", "注释", "初始值"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setItemDelegateForColumn(self.COL_CATEGORY, FbVariableCategoryDelegate(self._table))
        self._table.setItemDelegateForColumn(self.COL_DTYPE, DataTypeDelegate(self._table))
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.verticalHeader().setDefaultSectionSize(variable_table_row_height(self._table))
        root.addWidget(self._table, 1)

    def set_fb_context(self, name: str | None) -> None:
        n = (name or "").strip()
        self._header.setText(f"FB 变量定义 — {n}" if n else "FB 变量定义")

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
            c = (value or "VAR").strip().upper()
            variable.category = c if c in VARIABLE_CATEGORIES else "VAR"
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
        rh = variable_table_row_height(self._table)
        for row in range(self._table.rowCount()):
            self._table.setRowHeight(row, rh)
        self._table.blockSignals(False)
        self._applying = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._applying:
            return
        self.update_cell(item.row(), item.column(), item.text())


class StructuredTextEditor(QWidget):
    modified = Signal()

    def __init__(self, parent=None, *, show_comment_button: bool = True) -> None:
        super().__init__(parent)
        self._symbol_index: ProgramSymbolIndex | None = None
        self._function_block = None
        self._program_unit: ProgramUnit | None = None
        self._unknowns: list[str] = []
        self._refreshing_unknowns = False
        self._skip_next_completion_flush = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self._hint_label = QLabel("ST 结构化文本")
        self._hint_label.setStyleSheet("font-weight: 700; color: #244C7B;")
        self._create_symbol_btn = QPushButton("创建当前变量", header)
        self._create_symbol_btn.setProperty("compact", "true")
        self._create_symbol_btn.clicked.connect(self.create_current_symbol)
        self._format_btn = QPushButton("格式化", header)
        self._format_btn.setProperty("compact", "true")
        self._format_btn.setToolTip("整理换行、行尾空白；Tab 按四空格展开（不改语义）")
        self._format_btn.clicked.connect(self.format_document)
        self._comment_btn: QPushButton | None = None
        if show_comment_button:
            self._comment_btn = QPushButton("注释 (*)", header)
            self._comment_btn.setProperty("compact", "true")
            self._comment_btn.setToolTip("插入或包围 IEC 行注释 (* … *)")
            self._comment_btn.clicked.connect(self.insert_comment_snippet)
        header_layout.addWidget(self._hint_label, 0)
        header_layout.addStretch(1)
        header_layout.addWidget(self._format_btn, 0)
        if self._comment_btn is not None:
            header_layout.addWidget(self._comment_btn, 0)
        header_layout.addWidget(self._create_symbol_btn, 0)
        root.addWidget(header, 0)

        self._completion_list = QListWidget(self)
        self._completion_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._completion_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._completion_list.setMaximumHeight(220)
        self._completion_list.hide()
        self._completion_list.itemActivated.connect(lambda item: self.insert_completion(item.text()))

        self._editor_host = QWidget(self)
        _eh = QHBoxLayout(self._editor_host)
        _eh.setContentsMargins(0, 0, 0, 0)
        _eh.setSpacing(0)
        self._editor = _StPlainTextEdit(self._editor_host)
        self._line_number_area = _StLineNumberArea(self._editor, self._editor_host)
        _eh.addWidget(self._line_number_area, 0)
        _eh.addWidget(self._editor, 1)
        self._editor.set_completion_nav_callback(self._try_completion_nav)
        self._editor.setPlaceholderText(
            "等宽编辑：Tab 四空格；行尾 Enter 时：若本行仅一处裸 = 且可判断为赋值则改为 :=，"
            "并按规则补 ;（THEN/ELSE 等除外）；Ctrl+/ 行注释；"
            "补全：光标左侧为字母/数字/_ 时按标识符前缀匹配（Ctrl+Space 可强制）；"
            "↑↓/PgUp/PgDn、Enter/Tab 接受、Esc 关闭；成对符号内 Backspace 一次删一对。"
        )
        try:
            fx = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        except (AttributeError, TypeError):
            fx = QFont("Consolas", 10)
        if not QFontInfo(fx).exactMatch():
            fx = QFont("Consolas", 10)
        if not QFontInfo(fx).exactMatch():
            fx = QFont("Courier New", 10)
        self._editor.setFont(fx)
        self._line_number_area._on_block_geometry_changed()
        self._apply_st_tab_width()
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.cursorPositionChanged.connect(self._on_cursor_position_changed)
        self._editor.verticalScrollBar().valueChanged.connect(self._update_completion_geometry_if_visible)
        root.addWidget(self._editor_host, 1)

        self._highlighter = _StSyntaxHighlighter(self._editor.document())
        self._editor.set_editor_chord_callbacks(
            toggle_line_comment=self.toggle_line_comment,
            force_completion=self._force_completion_panel,
        )
        self.setFocusProxy(self._editor)
        self._complete_timer = QTimer(self)
        self._complete_timer.setSingleShot(True)
        self._complete_timer.setInterval(95)
        self._complete_timer.timeout.connect(self._flush_completion_panel)
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
        if function_block is not None:
            self._hint_label.setText(f"ST — {function_block.name}")
        elif program_unit is not None:
            self._hint_label.setText(f"ST — {program_unit.name}")
        else:
            self._hint_label.setText("ST 结构化文本")
        self._refresh_unknowns()

    def set_source(self, source: str) -> None:
        self._editor.setPlainText(source)
        self._line_number_area._on_block_geometry_changed()
        self._apply_st_tab_width()
        self._refresh_unknowns()

    def source(self) -> str:
        return self._editor.toPlainText()

    def _apply_st_tab_width(self) -> None:
        """与物理四空格缩进对齐的 Tab 显示宽度。"""
        fm = QFontMetrics(self._editor.font())
        w = max(8, fm.horizontalAdvance(" ") * ST_TAB_SPACES)
        self._editor.setTabStopDistance(float(w))

    def format_document(self) -> None:
        """一键整理 ST 文本（换行、行尾空白、Tab 展开、压缩多余空行）。"""
        cur = self._editor.textCursor()
        pos = cur.position()
        text = format_st_document(self._editor.toPlainText(), tab_columns=ST_TAB_SPACES)
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        cur.setPosition(min(pos, len(text)))
        self._editor.setTextCursor(cur)
        self._apply_st_tab_width()
        self._line_number_area._on_block_geometry_changed()
        self._refresh_unknowns()
        self._refresh_current_line_highlight()
        self._complete_timer.start()
        self.modified.emit()

    def insert_snippet(self, text: str) -> None:
        """在光标处插入文本（用于 ST 快捷结构）。"""
        cursor = self._editor.textCursor()
        cursor.insertText(text)
        self._editor.setTextCursor(cursor)
        self._on_text_changed()

    def completion_items(self, prefix: str) -> list[SuggestionItem]:
        if not (prefix or "").strip():
            return []
        if self._symbol_index is None:
            base: list[SuggestionItem] = []
        else:
            base = self._symbol_index.suggestions(
                prefix,
                mode="st",
                function_block=self._function_block,
                program_unit=self._program_unit,
            )
        lower = prefix.casefold()
        merged: dict[str, SuggestionItem] = {s.text.casefold(): s for s in base}
        if lower:
            for kw in ST_KEYWORDS:
                kf = kw.casefold()
                if kf in merged:
                    continue
                if kf.startswith(lower):
                    merged[kf] = SuggestionItem(kw, "keyword")
        ranked = sorted(
            merged.values(),
            key=lambda s: (
                0 if s.text.casefold().startswith(lower) else 1,
                0 if s.source != "keyword" else 1,
                s.text.casefold(),
            ),
        )
        return ranked

    def insert_comment_snippet(self) -> None:
        """插入 `(*  *)` 或将选中片段包入行注释。"""
        cur = self._editor.textCursor()
        if cur.hasSelection():
            t = cur.selectedText().replace("\u2029", "\n")
            cur.insertText(f"(* {t} *)")
        else:
            cur.insertText("(*  *)")
            for _ in range(3):
                cur.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor)
            self._editor.setTextCursor(cur)
        self._on_text_changed()

    def toggle_line_comment(self) -> None:
        """当前行或选区内各行整行切换 ``(* … *)``（与「注释 (*)」按钮风格一致）。"""
        doc = self._editor.document()
        cur = self._editor.textCursor()
        cur.beginEditBlock()
        try:
            if cur.hasSelection():
                start_bn = doc.findBlock(cur.selectionStart()).blockNumber()
                end_bn = doc.findBlock(cur.selectionEnd()).blockNumber()
            else:
                start_bn = end_bn = cur.blockNumber()
            for bn in range(start_bn, end_bn + 1):
                blk = doc.findBlockByNumber(bn)
                line = blk.text()
                new_line = toggle_st_line_comment(line)
                if new_line == line:
                    continue
                tc = QTextCursor(blk)
                tc.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                tc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                tc.removeSelectedText()
                tc.insertText(new_line)
        finally:
            cur.endEditBlock()
        self._on_text_changed()

    def unknown_identifiers(self) -> list[str]:
        return list(self._unknowns)

    def suggestion_texts(self) -> list[str]:
        return [self._completion_list.item(index).text() for index in range(self._completion_list.count())]

    def show_completion_panel(self, prefix: str | None = None, *, _relax_identifier_gate: bool = False) -> None:
        if not _relax_identifier_gate:
            ch = self._char_before_cursor_on_line()
            if ch is None or not (ch.isalnum() or ch == "_"):
                self._completion_list.hide()
                return
        token = self._current_prefix() if prefix is None else prefix
        if not token:
            self._completion_list.hide()
            return
        items = self.completion_items(token)
        self._completion_list.clear()
        if not items:
            self._completion_list.hide()
            return
        for item in items:
            label = f"{item.text}"
            if item.source and item.source != "keyword":
                label = f"{item.text}  ({item.source})"
            self._completion_list.addItem(label)
        self._completion_list.setVisible(bool(items))
        if items:
            self._completion_list.setCurrentRow(0)
        self._update_completion_geometry()

    def _force_completion_panel(self) -> None:
        self._skip_next_completion_flush = False
        self._complete_timer.stop()
        self.show_completion_panel(_relax_identifier_gate=True)

    def _try_completion_nav(self, event: QKeyEvent) -> bool:
        """补全列表可见时拦截 ↑↓、Enter、Tab、Esc（由编辑器接收按键）。"""
        if not self._completion_list.isVisible() or self._completion_list.count() == 0:
            return False
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Escape and mods == Qt.KeyboardModifier.NoModifier:
            self._complete_timer.stop()
            self._completion_list.hide()
            self._skip_next_completion_flush = True
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            bare = mods & ~Qt.KeyboardModifier.KeypadModifier
            if bare != Qt.KeyboardModifier.NoModifier:
                return False
            self._accept_current_completion()
            return True
        if key == Qt.Key.Key_Tab and mods == Qt.KeyboardModifier.NoModifier:
            self._accept_current_completion()
            return True
        if key == Qt.Key.Key_Down and mods == Qt.KeyboardModifier.NoModifier:
            self._completion_row_delta(1)
            return True
        if key == Qt.Key.Key_Up and mods == Qt.KeyboardModifier.NoModifier:
            self._completion_row_delta(-1)
            return True
        if key == Qt.Key.Key_PageDown and mods == Qt.KeyboardModifier.NoModifier:
            self._completion_row_delta(self._completion_page_step())
            return True
        if key == Qt.Key.Key_PageUp and mods == Qt.KeyboardModifier.NoModifier:
            self._completion_row_delta(-self._completion_page_step())
            return True
        return False

    def _completion_page_step(self) -> int:
        lw = self._completion_list
        n = lw.count()
        if n <= 0:
            return 1
        fm = lw.fontMetrics()
        row_h = max(8, fm.height() + 2)
        vis_h = lw.viewport().height() or lw.maximumHeight()
        vis_h = max(vis_h, row_h * 2)
        step = max(1, vis_h // row_h)
        return min(step, max(1, n - 1))

    def _completion_row_delta(self, delta: int) -> None:
        n = self._completion_list.count()
        if n <= 0:
            return
        row = max(0, min(n - 1, self._completion_list.currentRow() + delta))
        self._completion_list.setCurrentRow(row)
        self._update_completion_geometry_if_visible()

    def _accept_current_completion(self) -> None:
        item = self._completion_list.currentItem()
        if item is None:
            return
        self.insert_completion(item.text())

    def insert_completion(self, value: str) -> None:
        self._complete_timer.stop()
        self._completion_list.hide()
        self._skip_next_completion_flush = True
        cursor = self._editor.textCursor()
        token = self._current_prefix()
        insert_text = value.split("  (", 1)[0].strip()
        for _ in range(len(token)):
            cursor.deletePreviousChar()
        cursor.insertText(insert_text)
        self._editor.setTextCursor(cursor)

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
        self._complete_timer.start()
        self.modified.emit()

    def _on_cursor_position_changed(self) -> None:
        self._refresh_current_line_highlight()
        self._complete_timer.start()
        self._update_completion_geometry_if_visible()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_completion_geometry_if_visible()

    def _update_completion_geometry_if_visible(self) -> None:
        if not self._completion_list.isVisible() or self._completion_list.count() == 0:
            return
        self._update_completion_geometry()

    def _update_completion_geometry(self) -> None:
        """补全列表浮动在光标附近（相对本控件坐标），避免占满底部栏。"""
        vp = self._editor.viewport()
        cr = self._editor.cursorRect()
        bottom_local = vp.mapTo(self, cr.bottomLeft())
        top_local = vp.mapTo(self, cr.topLeft())
        margin = 2
        x = bottom_local.x()
        y = bottom_local.y() + margin
        fm = self._completion_list.fontMetrics()
        row_h = max(22, fm.height() + 8)
        n_items = self._completion_list.count()
        # 至少留出 4 行可视高度，避免只有 1～3 条时补全框过扁
        rows_for_height = max(n_items, 4)
        content_h = 8 + rows_for_height * row_h
        scr = QGuiApplication.primaryScreen()
        try:
            avail_h = int(scr.availableGeometry().height()) if scr is not None else 1080
        except (AttributeError, RuntimeError):
            avail_h = 1080
        # 上限随工作区高度放宽（约 80% 可用高度，且不低于 720px）
        max_list_h = max(720, int(avail_h * 0.8))
        list_h = min(max_list_h, max(row_h + 8, content_h))
        sw = 0
        for i in range(self._completion_list.count()):
            it = self._completion_list.item(i)
            if it is not None:
                sw = max(sw, fm.horizontalAdvance(it.text()) + 24)
        w = max(200, min(max(sw, 200), self.width() - 12))
        if y + list_h > self.height() - 2:
            y2 = top_local.y() - margin - list_h
            if y2 >= 2:
                y = y2
        max_x = max(4, self.width() - w - 4)
        x = max(4, min(x, max_x))
        max_y = max(4, self.height() - list_h - 2)
        y = max(4, min(y, max_y))
        self._completion_list.setFixedSize(w, list_h)
        self._completion_list.move(x, y)
        self._completion_list.raise_()

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

    def _char_before_cursor_on_line(self) -> str | None:
        """光标所在行、插入点左侧紧邻的一个字符（用于判断是否正在输入标识符）。"""
        cur = self._editor.textCursor()
        t = cur.block().text()
        p = cur.positionInBlock()
        if p <= 0:
            return None
        return t[p - 1]

    def _current_prefix(self) -> str:
        """自光标左侧紧邻字符起向左连续读取 [A-Za-z0-9_]，形成用于前缀匹配（``startswith``）的字符串。

        若插入点左侧不是标识符字符，返回空串，自动补全不弹出。
        """
        cursor = self._editor.textCursor()
        block_text = cursor.block().text()
        position = cursor.positionInBlock()
        if position <= 0:
            return ""
        if not (block_text[position - 1].isalnum() or block_text[position - 1] == "_"):
            return ""
        prefix: list[str] = []
        index = position - 1
        while index >= 0:
            char = block_text[index]
            if not (char.isalnum() or char == "_"):
                break
            prefix.append(char)
            index -= 1
        return "".join(reversed(prefix))

    def _flush_completion_panel(self) -> None:
        if self._skip_next_completion_flush:
            self._skip_next_completion_flush = False
            self._completion_list.hide()
            self._complete_timer.stop()
            return
        token = self._current_prefix()
        if not token:
            self._completion_list.hide()
            return
        self.show_completion_panel(token)

    def _refresh_current_line_highlight(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#EAF3FF"))
        selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selection.cursor = self._editor.textCursor()
        selection.cursor.clearSelection()
        self._editor.setExtraSelections([selection])


