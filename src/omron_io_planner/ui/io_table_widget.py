# -*- coding: utf-8 -*-
"""
Excel 风格的 IO 表格组件。

阶段一功能：
- 模块1：单元格编辑交互
  - F2 进入编辑
  - 直接打字开始编辑（覆盖原内容）
  - Escape 退出编辑恢复原内容
  - 编辑时粗边框高亮
- 模块2：选区与导航
  - Shift+方向键 扩展/收缩选区
  - Ctrl+方向键 跳到数据边缘
  - Ctrl+Shift+方向键 跳到边缘并扩展选区
  - Ctrl+A 全选
  - Ctrl+Home/End 跳到数据范围角
  - Tab 到行末自动换行回第一列+1行
  - Enter 记住列向下移动
  - Ctrl+C/V/X/D/Y/Z/Delete 复制粘贴剪切填充撤销重做清除
- 模块3：选区视觉效果（部分）
  - 选区蓝色粗边框
  - 当前单元格粗边框
  - 填充手柄（右下角蓝色小方块）
- 模块4：填充功能
  - 拖拽填充（向下）
  - Ctrl+D 向下填充
  - Ctrl+R 向右填充
  - 地址列欧姆龙规则递增
- 模块5：右键菜单（已优化）
  - 插入/删除行
  - 复制/剪切/粘贴/清除
  - 填充选项
- 名称列智能补全：根据表内已有名称预测相反方向（上→下、开→关、…）
"""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import (
    QMimeData,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QKeySequence,
    QPainter,
    QPen,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QLineEdit,
    QMenu,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
)

from .highlight_header_view import _HighlightHeaderView
from ..addressing import format_cio_bit, parse_cio_bit

# ──────────────────────────────────────────────────────────────────────────────
# 名称智能预测配对表（双向）
# ──────────────────────────────────────────────────────────────────────────────
_PAIR_TABLE: list[tuple[str, str]] = [
    ("上", "下"),
    ("下", "上"),
    ("左", "右"),
    ("右", "左"),
    ("开", "关"),
    ("关", "开"),
    ("启", "停"),
    ("停", "启"),
    ("正转", "反转"),
    ("反转", "正转"),
    ("前进", "后退"),
    ("后退", "前进"),
    ("上升", "下降"),
    ("下降", "上升"),
    ("伸出", "缩回"),
    ("缩回", "伸出"),
    ("夹紧", "松开"),
    ("松开", "夹紧"),
    ("吹气", "停气"),
    ("停气", "吹气"),
    ("进", "出"),
    ("出", "进"),
    ("高", "低"),
    ("低", "高"),
    ("快", "慢"),
    ("慢", "快"),
    ("到位", "离位"),
    ("离位", "到位"),
    ("到位", "原位"),
    ("原位", "到位"),
    ("复位", "工作位"),
    ("工作位", "复位"),
    ("有料", "无料"),
    ("无料", "有料"),
    ("满", "空"),
    ("空", "满"),
    ("ON", "OFF"),
    ("OFF", "ON"),
    ("In", "Out"),
    ("Out", "In"),
    ("Fwd", "Rev"),
    ("Rev", "Fwd"),
    ("Up", "Down"),
    ("Down", "Up"),
    ("Open", "Close"),
    ("Close", "Open"),
    ("Start", "Stop"),
    ("Stop", "Start"),
    ("Extend", "Retract"),
    ("Retract", "Extend"),
    ("Clamp", "Release"),
    ("Release", "Clamp"),
]


def _predict_name(existing_names: list[str], prefix: str) -> str | None:
    """
    根据 existing_names 中的规律，为含 prefix 的输入预测下一个名称。
    例如：已有 "传送带_上"，输入 "传送带_"，预测 "传送带_下"。
    """
    if not prefix:
        return None
    candidates = [n for n in existing_names if n.startswith(prefix) and n != prefix]
    if not candidates:
        return None
    for cand in reversed(candidates):
        suffix = cand[len(prefix):]
        best_suggestion: str | None = None
        best_score: tuple[int, int, int] | None = None
        for src, tgt in _PAIR_TABLE:
            start = suffix.find(src)
            while start >= 0:
                suggestion = prefix + suffix[:start] + tgt + suffix[start + len(src):]
                if suggestion not in existing_names:
                    score = (1 if start == 0 else 0, len(src), -start)
                    if best_score is None or score > best_score:
                        best_score = score
                        best_suggestion = suggestion
                start = suffix.find(src, start + 1)
        if best_suggestion is not None:
            return best_suggestion
    return None


def _flip_phrase(text: str) -> str | None:
    best_suggestion: str | None = None
    best_score: tuple[int, int, int] | None = None
    for src, tgt in _PAIR_TABLE:
        start = text.find(src)
        while start >= 0:
            suggestion = text[:start] + tgt + text[start + len(src):]
            if suggestion != text:
                score = (1 if start == 0 else 0, len(src), -start)
                if best_score is None or score > best_score:
                    best_score = score
                    best_suggestion = suggestion
            start = text.find(src, start + 1)
    return best_suggestion


def _all_names_in_table(table: "IoTableWidget", col_name: int = 0) -> list[str]:
    names = []
    for r in range(table.rowCount()):
        item = table.item(r, col_name)
        if item:
            t = item.text().strip()
            if t:
                names.append(t)
    return names


# ──────────────────────────────────────────────────────────────────────────────
# 欧姆龙地址自动填充
# ──────────────────────────────────────────────────────────────────────────────

def _next_omron_bit(addr: str) -> str | None:
    """
    欧姆龙地址递增逻辑：
    - 同字内 bit+1（到 .15 为止）
    - bit 超过 15 时进到下一字的 .00
    """
    t = parse_cio_bit(addr)
    if t is None:
        return None
    w, b = t
    nb = b + 1
    if nb > 15:
        return format_cio_bit(w + 1, 0)
    return format_cio_bit(w, nb)


def _omron_add(addr: str, delta: int) -> str:
    """地址列增加指定步长（地址列步长填充专用）"""
    t = parse_cio_bit(addr)
    if t is None:
        return addr
    w, b = t
    total_bits = w * 16 + b + delta
    if total_bits < 0:
        return addr
    new_w = total_bits // 16
    new_b = total_bits % 16
    return format_cio_bit(new_w, new_b)


# ──────────────────────────────────────────────────────────────────────────────
# 自定义委托：支持 Escape 恢复原内容
# ──────────────────────────────────────────────────────────────────────────────

class _ExcelDelegate(QStyledItemDelegate):
    """支持 Escape 恢复原内容的编辑委托"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._editing_orig_text: str | None = None

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            table = self.parent()
            background = _cell_background_color(table if isinstance(table, IoTableWidget) else None, index.row())
            _prepare_inline_line_edit(editor, background)
            # 记录编辑前的原始文本（用于 Escape 恢复）
            item = index.model().index(index.row(), index.column()).data(Qt.ItemDataRole.DisplayRole)
            self._editing_orig_text = str(item) if item is not None else ""
        return editor

    def setEditorData(self, editor, index):
        super().setEditorData(editor, index)
        if isinstance(editor, QLineEdit):
            if self._editing_orig_text is not None:
                # 原始数据已保存，无需额外处理
                pass

    def setModelData(self, editor, model, index):
        # 处理地址列的特殊输入：.xx 自动补为 0.xx
        # 地址列是索引 2 (COL_ADDR)
        if index.column() == 2 and isinstance(editor, QLineEdit):
            text = editor.text().strip()
            if text.startswith('.'):
                # .01 → 0.01, .15 → 0.15
                text = '0' + text
            table = self.parent()
            if isinstance(table, IoTableWidget):
                table.commit_editor_text(index.row(), index.column(), text)
                self._editing_orig_text = None
                return

        if isinstance(editor, QLineEdit):
            table = self.parent()
            if isinstance(table, IoTableWidget):
                table.commit_editor_text(index.row(), index.column(), editor.text())
                self._editing_orig_text = None
                return

        super().setModelData(editor, model, index)
        # 编辑完成后清除原始文本记录
        self._editing_orig_text = None

    def get_orig_text(self) -> str | None:
        return self._editing_orig_text


# ──────────────────────────────────────────────────────────────────────────────
# Undo/Redo 命令
# ──────────────────────────────────────────────────────────────────────────────

class _CellEditCommand(QUndoCommand):
    def __init__(
        self,
        table: "IoTableWidget",
        row: int,
        col: int,
        old_text: str,
        new_text: str,
    ) -> None:
        super().__init__(f"编辑 ({row},{col})")
        self._table = table
        self._row = row
        self._col = col
        self._old = old_text
        self._new = new_text

    def redo(self) -> None:
        self._set(self._new)

    def undo(self) -> None:
        self._set(self._old)

    def _set(self, text: str) -> None:
        self._table.blockSignals(True)
        item = self._table.item(self._row, self._col)
        if item is None:
            item = QTableWidgetItem(text)
            self._table.setItem(self._row, self._col, item)
        else:
            item.setText(text)
        self._table.blockSignals(False)
        self._table._after_batch_change("edit", self._row)


class _MultiCellCommand(QUndoCommand):
    """批量单元格操作（粘贴/清除/填充）。"""

    def __init__(
        self,
        table: "IoTableWidget",
        changes: list[tuple[int, int, str, str]],  # (row, col, old, new)
        description: str = "批量编辑",
        reason: str = "batch_edit",
    ) -> None:
        super().__init__(description)
        self._table = table
        self._changes = changes
        self._reason = reason

    def redo(self) -> None:
        self._apply(new=True)

    def undo(self) -> None:
        self._apply(new=False)

    def _apply(self, new: bool) -> None:
        self._table.blockSignals(True)
        for row, col, old, nw in self._changes:
            text = nw if new else old
            item = self._table.item(row, col)
            if item is None:
                item = QTableWidgetItem(text)
                self._table.setItem(row, col, item)
            else:
                item.setText(text)
        self._table.blockSignals(False)
        max_row = max((row for row, *_ in self._changes), default=None)
        self._table._after_batch_change(self._reason, max_row)


class _MoveRowsCommand(QUndoCommand):
    """行移动撤销命令（阶段四）"""

    def __init__(
        self,
        table: "IoTableWidget",
        rows: list[int],
        target_row: int,
        row_data: list[list[dict]],
    ) -> None:
        super().__init__("移动行")
        self._table = table
        self._rows = sorted(rows)
        self._target_row = target_row
        self._row_data = row_data

    def redo(self) -> None:
        self._table.blockSignals(True)
        # 移除旧行
        for row in reversed(sorted(self._rows)):
            self._table.removeRow(row)

        # 在目标位置插入新行
        insert_pos = self._target_row
        # 调整插入位置（考虑删除后的索引变化）
        for row in sorted(self._rows):
            if row < self._target_row:
                insert_pos -= 1

        for data in self._row_data:
            self._table.insertRow(insert_pos)
            for col, col_data in enumerate(data):
                if col_data:
                    item = QTableWidgetItem(col_data["text"])
                    item.setFlags(col_data["flags"])
                    if col_data["background"]:
                        item.setBackground(col_data["background"])
                    if col_data["foreground"]:
                        item.setForeground(col_data["foreground"])
                    self._table.setItem(insert_pos, col, item)
                else:
                    self._table.setItem(insert_pos, col, QTableWidgetItem(""))
            insert_pos += 1
        self._table.blockSignals(False)
        self._table._after_batch_change("move_rows")

    def undo(self) -> None:
        self._table.blockSignals(True)
        # 删除插入的行
        start_pos = self._target_row
        # 调整起始位置
        for row in sorted(self._rows):
            if row < self._target_row:
                start_pos -= 1

        for _ in self._row_data:
            self._table.removeRow(start_pos)

        # 恢复旧行
        for row, data in zip(sorted(self._rows), self._row_data):
            self._table.insertRow(row)
            for col, col_data in enumerate(data):
                if col_data:
                    item = QTableWidgetItem(col_data["text"])
                    item.setFlags(col_data["flags"])
                    if col_data["background"]:
                        item.setBackground(col_data["background"])
                    if col_data["foreground"]:
                        item.setForeground(col_data["foreground"])
                    self._table.setItem(row, col, item)
                else:
                    self._table.setItem(row, col, QTableWidgetItem(""))
        self._table.blockSignals(False)
        self._table._after_batch_change("move_rows")


# ──────────────────────────────────────────────────────────────────────────────
# 填充手柄尺寸常量
# ──────────────────────────────────────────────────────────────────────────────
_HANDLE_SIZE = 8   # 填充手柄边长（像素）
_HANDLE_HIT  = 14  # 命中区域边长（更容易点中）
_MIN_VISIBLE_ROWS = 50
_TAIL_BUFFER_ROWS = 20
_TAIL_TRIGGER_ROWS = 10
_CELL_BG = "#FFFFFF"
_CELL_ALT_BG = "#EEF2FF"
_TEXT_NUMBER_RE = re.compile(r"^(.*?)(\d+)(\D*)$")
_TEMPLATE_NUMBER_RE = re.compile(r"\{(?:n|num)(?::(\d+))?\}")
_TEMPLATE_ALT_RE = re.compile(r"\[([^\[\]\|]+)\|([^\[\]\|]+)\]")


def _cell_background_color(table: "IoTableWidget | None", row: int | None) -> str:
    if table is not None and row is not None and table.alternatingRowColors() and row % 2 == 1:
        return _CELL_ALT_BG
    return _CELL_BG


def _inline_line_edit_stylesheet(background_color: str = _CELL_BG) -> str:
    return (
        "QLineEdit {"
        " border: none;"
        f" background-color: {background_color};"
        " padding: 0 2px;"
        " margin: 0;"
        " color: #1E2235;"
        " selection-background-color: rgba(74,111,165,0.18);"
        " selection-color: #1E2235;"
        "}"
        "QLineEdit:focus {"
        " border: none;"
        " outline: none;"
        f" background-color: {background_color};"
        "}"
    )


def _prepare_inline_line_edit(editor: QLineEdit, background_color: str = _CELL_BG) -> QLineEdit:
    editor.setFrame(False)
    editor.setAutoFillBackground(True)
    editor.setStyleSheet(_inline_line_edit_stylesheet(background_color))
    return editor


def _parse_numbered_text(text: str) -> tuple[str, int, str, int] | None:
    match = _TEXT_NUMBER_RE.match(text)
    if not match:
        return None
    prefix, number_text, suffix = match.groups()
    return prefix, int(number_text), suffix, len(number_text)


def _build_text_fill_values(
    source_values: list[str],
    count: int,
    *,
    reverse: bool = False,
) -> list[str] | None:
    if count <= 0:
        return []

    values = [value for value in source_values if value]
    if not values:
        return None

    parsed = [_parse_numbered_text(value) for value in values]
    if all(part is not None for part in parsed):
        normalized = [part for part in parsed if part is not None]
        prefixes = {part[0] for part in normalized}
        suffixes = {part[2] for part in normalized}
        if len(prefixes) == 1 and len(suffixes) == 1:
            prefix = normalized[0][0]
            suffix = normalized[0][2]
            width = max(part[3] for part in normalized)
            numbers = [part[1] for part in normalized]

            step = 1
            if len(numbers) >= 2:
                deltas = [numbers[idx] - numbers[idx - 1] for idx in range(1, len(numbers))]
                nonzero = [delta for delta in deltas if delta != 0]
                step = nonzero[-1] if nonzero else 1

            if reverse:
                anchor = numbers[0]
                sequence = [anchor - step * offset for offset in range(count, 0, -1)]
            else:
                anchor = numbers[-1]
                sequence = [anchor + step * offset for offset in range(1, count + 1)]

            return [f"{prefix}{number:0{width}d}{suffix}" for number in sequence]

    pair_values = _build_pair_fill_values(values, count, reverse=reverse)
    if pair_values is not None:
        return pair_values
    return None


def _build_pair_fill_values(
    source_values: list[str],
    count: int,
    *,
    reverse: bool = False,
) -> list[str] | None:
    base = [value.strip() for value in source_values if value and value.strip()]
    if not base:
        return None
    if len(base) == 1:
        flipped = _flip_phrase(base[0])
        if not flipped:
            return None
        pattern = [base[0], flipped]
    else:
        first = base[-2]
        second = base[-1]
        flipped = _flip_phrase(first)
        if flipped != second:
            return None
        pattern = [first, second]

    base_len = len(base)
    if reverse:
        return [pattern[(base_len - offset - 1) % 2] for offset in range(count, 0, -1)]
    return [pattern[(base_len + offset) % 2] for offset in range(count)]


def _render_generation_template(template: str, index: int, address: str = "") -> str:
    if not template:
        return ""
    rendered = template.replace("{addr}", address)

    def _replace_number(match: re.Match[str]) -> str:
        width = int(match.group(1) or 0)
        number = index + 1
        return f"{number:0{width}d}" if width > 0 else str(number)

    rendered = _TEMPLATE_NUMBER_RE.sub(_replace_number, rendered)
    rendered = _TEMPLATE_ALT_RE.sub(
        lambda match: match.group(1) if index % 2 == 0 else match.group(2),
        rendered,
    )
    return rendered


# ──────────────────────────────────────────────────────────────────────────────
# 主 Widget
# ──────────────────────────────────────────────────────────────────────────────

class IoTableWidget(QTableWidget):
    """
    Excel 风格 IO 表格（阶段一+二+三+四）：
    - Ctrl+C / Ctrl+V / Ctrl+X / Delete / Tab / Enter / 方向键
    - F2 进入编辑
    - 直接打字开始编辑（覆盖原内容）
    - Escape 恢复原内容
    - Shift+方向键 扩展选区
    - Ctrl+方向键 跳到数据边缘
    - Ctrl+A 全选
    - Ctrl+Home/End 跳到数据范围角
    - Tab 行末换行
    - Enter 记住列向下
    - 选区视觉效果：蓝色粗边框、当前单元格深蓝边框、复制蚂蚁线
    - 行列头高亮（Excel 风格橙色）
    - 右键菜单
    - **四向拖拽填充**（阶段三）：向下、向上、向右、向左
    - **地址列步长检测**（阶段三）：选 2+ 行时自动检测步长并按步长填充
    - Ctrl+D/R 填充
    - 名称列智能补全
    - Undo/Redo
    - **整行选择**（阶段四）：点击行头选中整行，支持 Ctrl/Shift 组合
    """

    contentDirty = Signal(str)

    COL_NAME    = 0
    COL_DTYPE   = 1
    COL_ADDR    = 2
    COL_COMMENT = 3
    COL_RACK    = 4
    COL_USAGE   = 5

    def __init__(self, parent=None) -> None:
        super().__init__(0, 6, parent)
        self._undo_stack = QUndoStack(self)
        self._ignore_change = False
        self._editor_defaults = {
            "continuous_entry": False,
            "enter_navigation": "down",
            "tab_navigation": "right",
            "auto_increment_address": False,
            "inherit_data_type": False,
            "inherit_rack": False,
            "inherit_usage": False,
            "auto_increment_name": False,
            "auto_increment_comment": False,
            "suggestions_enabled": True,
            "suggestion_limit": 8,
            "row_height": 34,
        }
        self._name_phrase_library: list[str] = []
        self._comment_phrase_library: list[str] = []

        # 拖拽填充状态
        self._fill_dragging   = False     # 是否正在拖拽填充手柄
        self._fill_drag_start_row = -1    # 拖拽起始行（选区最后一行）
        self._fill_drag_start_col_min = -1
        self._fill_drag_start_col_max = -1
        self._fill_preview_row = -1       # 预览填充到第几行（蓝色虚线框）
        self._fill_preview_col = -1       # 预览填充到第几列（蓝色虚线框，四向填充）
        self._fill_sel_r0 = -1
        self._fill_sel_r1 = -1
        self._fill_sel_c0 = -1
        self._fill_sel_c1 = -1

        # 复制选区蚂蚁线（Ctrl+C 后显示虚线边框）
        self._copied_rect: tuple[int, int, int, int] | None = None

        # Enter 记住的列（Excel 默认记住 Enter 触发时的列）
        self._enter_column: int | None = None
        self._addr_sort_order: Qt.SortOrder | None = None

        # 行拖拽排序状态
        self._row_drag_start_index: QModelIndex | None = None
        self._row_drag_drop_position: int | None = None

        # 自定义委托
        self._delegate = _ExcelDelegate(self)
        self.setItemDelegate(self._delegate)

        # 替换为自定义行列头（支持高亮）
        self.setHorizontalHeader(_HighlightHeaderView(Qt.Orientation.Horizontal, self))
        self.setVerticalHeader(_HighlightHeaderView(Qt.Orientation.Vertical, self))
        horizontal_header = self.horizontalHeader()
        horizontal_header.sectionActivated.connect(self._on_header_section_clicked)
        horizontal_header.setSortIndicatorShown(False)

        self.setHorizontalHeaderLabels(["名称", "数据类型", "地址/值", "注释", "机架位置", "使用"])
        self.horizontalHeader().setSectionResizeMode(self.COL_COMMENT, _HighlightHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(self.COL_NAME, _HighlightHeaderView.ResizeMode.Interactive)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.setTabKeyNavigation(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalHeader().setDefaultSectionSize(int(self._editor_defaults["row_height"]))

        # 启用行拖拽排序（阶段四）
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

        # 仅保留填充手柄拖拽，不启用整行拖拽
        self.viewport().setMouseTracking(True)

        self.itemChanged.connect(self._on_item_changed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.setColumnWidth(self.COL_NAME,   60)
        self.setColumnWidth(self.COL_DTYPE, 100)
        self.setColumnWidth(self.COL_ADDR,   96)
        self.setColumnWidth(self.COL_RACK,  100)
        self.setColumnWidth(self.COL_USAGE,  78)
        self._ensure_spare_rows()

    def editor_defaults(self) -> dict[str, object]:
        return dict(self._editor_defaults)

    def set_editor_defaults(self, values: dict[str, object]) -> None:
        self._editor_defaults.update(values)
        row_height = int(self._editor_defaults.get("row_height", 34) or 34)
        self.verticalHeader().setDefaultSectionSize(max(20, row_height))

    def set_phrase_library(self, name_phrases: list[str], comment_phrases: list[str]) -> None:
        self._name_phrase_library = [phrase.strip() for phrase in name_phrases if phrase and phrase.strip()]
        self._comment_phrase_library = [phrase.strip() for phrase in comment_phrases if phrase and phrase.strip()]

    def phrase_library_for_column(self, column: int) -> list[str]:
        if column == self.COL_NAME:
            return list(self._name_phrase_library)
        if column == self.COL_COMMENT:
            return list(self._comment_phrase_library)
        return []

    def suggestion_limit(self) -> int:
        return max(1, int(self._editor_defaults.get("suggestion_limit", 8) or 8))

    def suggestions_enabled(self) -> bool:
        return bool(self._editor_defaults.get("suggestions_enabled", True))

    # ── 撤销/重做 ──────────────────────────────────────────────────────────

    def undo(self) -> None:
        self._undo_stack.undo()

    def redo(self) -> None:
        self._undo_stack.redo()

    def _append_blank_rows(self, count: int) -> None:
        if count <= 0:
            return
        self.blockSignals(True)
        start = self.rowCount()
        self.setRowCount(start + count)
        for row in range(start, start + count):
            for col in range(self.columnCount()):
                if self.item(row, col) is None:
                    self.setItem(row, col, QTableWidgetItem(""))
        self.blockSignals(False)

    def _last_non_empty_row(self) -> int:
        for row in range(self.rowCount() - 1, -1, -1):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item and item.text().strip():
                    return row
        return -1

    def _ensure_spare_rows(self, anchor_row: int | None = None) -> None:
        last_data_row = self._last_non_empty_row()
        desired_rows = max(_MIN_VISIBLE_ROWS, last_data_row + 1 + _TAIL_BUFFER_ROWS)
        if anchor_row is not None and self.rowCount() - anchor_row <= _TAIL_TRIGGER_ROWS:
            desired_rows = max(desired_rows, self.rowCount() + _TAIL_BUFFER_ROWS)
        if self.rowCount() < desired_rows:
            self._append_blank_rows(desired_rows - self.rowCount())

    def _ensure_row_available(self, row: int) -> None:
        if row < self.rowCount():
            self._ensure_spare_rows(row)
            return
        self._append_blank_rows(row - self.rowCount() + 1)
        self._ensure_spare_rows(row)

    def _after_batch_change(self, reason: str, anchor_row: int | None = None) -> None:
        self._copied_rect = None
        self._ensure_spare_rows(anchor_row)
        self.viewport().update()
        self.contentDirty.emit(reason)

    def _snapshot_row_data(self, row: int) -> list[dict]:
        data: list[dict] = []
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item is None:
                data.append({})
                continue
            data.append(
                {
                    "text": item.text(),
                    "flags": item.flags(),
                    "background": item.background(),
                    "foreground": item.foreground(),
                }
            )
        return data

    def _restore_row_data(self, row: int, data: list[dict]) -> None:
        for col, col_data in enumerate(data):
            if col_data:
                item = self.item(row, col)
                if item is None:
                    item = QTableWidgetItem(col_data["text"])
                    self.setItem(row, col, item)
                item.setText(col_data["text"])
                item.setFlags(col_data["flags"])
                item.setBackground(col_data["background"])
                item.setForeground(col_data["foreground"])
            else:
                item = self.item(row, col)
                if item is None:
                    item = QTableWidgetItem("")
                    self.setItem(row, col, item)
                else:
                    item.setText("")

    def _row_has_visible_data(self, data: list[dict]) -> bool:
        return any(col_data and str(col_data.get("text", "")).strip() for col_data in data)

    def row_has_content(self, row: int) -> bool:
        if row < 0 or row >= self.rowCount():
            return False
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item and item.text().strip():
                return True
        return False

    def duplicate_selected_rows(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()})
        if not rows and self.currentIndex().isValid():
            rows = [self.currentRow()]
        if not rows:
            return

        snapshots = [self._snapshot_row_data(row) for row in rows]
        insert_at = rows[-1] + 1
        self.blockSignals(True)
        for offset, data in enumerate(snapshots):
            target_row = insert_at + offset
            self.insertRow(target_row)
            for col in range(self.columnCount()):
                if self.item(target_row, col) is None:
                    self.setItem(target_row, col, QTableWidgetItem(""))
            self._restore_row_data(target_row, data)
        self.blockSignals(False)

        self.clearSelection()
        for offset in range(len(snapshots)):
            self.selectRow(insert_at + offset)
        self.setCurrentCell(insert_at, self.currentColumn() if self.currentColumn() >= 0 else self.COL_NAME)
        self._after_batch_change("duplicate_rows", insert_at + len(snapshots) - 1)

    def selected_row_numbers(self) -> list[int]:
        rows = sorted({index.row() for index in self.selectedIndexes()})
        if not rows and self.currentIndex().isValid():
            rows = [self.currentRow()]
        return rows

    def bulk_update_selected_rows(self, updates: dict[str, str]) -> None:
        column_map = {
            "data_type": self.COL_DTYPE,
            "rack": self.COL_RACK,
            "usage": self.COL_USAGE,
        }
        rows = self.selected_row_numbers()
        if not rows:
            return
        changes: list[tuple[int, int, str, str]] = []
        for row in rows:
            for key, value in updates.items():
                if key not in column_map:
                    continue
                col = column_map[key]
                item = self.item(row, col)
                old = item.text() if item else ""
                if old != value:
                    changes.append((row, col, old, value))
        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "批量设置", "bulk_update"))

    def bulk_transform_selection(self, mode: str, value: str = "", start: int = 1) -> None:
        indices = sorted(
            {(index.row(), index.column()) for index in self.selectedIndexes()},
            key=lambda cell: (cell[0], cell[1]),
        )
        if not indices and self.currentIndex().isValid():
            indices = [(self.currentRow(), self.currentColumn())]
        if not indices:
            return
        changes: list[tuple[int, int, str, str]] = []
        counter = start
        for row, col in indices:
            item = self.item(row, col)
            old = item.text() if item else ""
            if not old:
                continue
            if mode == "prefix":
                new = f"{value}{old}"
            elif mode == "suffix":
                new = f"{old}{value}"
            elif mode == "number":
                new = f"{old}{counter}"
                counter += 1
            else:
                continue
            if old != new:
                changes.append((row, col, old, new))
        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "批量文本处理", "bulk_transform"))

    def apply_multi_changes(self, changes: list[tuple[int, int, str, str]], description: str, reason: str) -> None:
        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, description, reason))

    def layout_state(self) -> dict[str, object]:
        header = self.horizontalHeader()
        widths = [self.columnWidth(col) for col in range(self.columnCount())]
        visual_order = [header.visualIndex(col) for col in range(self.columnCount())]
        hidden = [self.isColumnHidden(col) for col in range(self.columnCount())]
        state: dict[str, object] = {
            "widths": widths,
            "visual_order": visual_order,
            "hidden": hidden,
        }
        if self._addr_sort_order is not None:
            state["sort"] = {
                "column": self.COL_ADDR,
                "order": "desc" if self._addr_sort_order == Qt.SortOrder.DescendingOrder else "asc",
            }
        return state

    def apply_layout_state(self, state: dict[str, object]) -> None:
        if not state:
            return
        widths = state.get("widths")
        if isinstance(widths, list):
            for col, width in enumerate(widths[: self.columnCount()]):
                self.setColumnWidth(col, int(width))
        hidden = state.get("hidden")
        if isinstance(hidden, list):
            for col, is_hidden in enumerate(hidden[: self.columnCount()]):
                self.setColumnHidden(col, bool(is_hidden))
        visual_order = state.get("visual_order")
        if isinstance(visual_order, list) and len(visual_order) == self.columnCount():
            header = self.horizontalHeader()
            target_positions = {logical: int(position) for logical, position in enumerate(visual_order)}
            for target_visual in range(self.columnCount()):
                logical = next(
                    (logical_index for logical_index, pos in target_positions.items() if pos == target_visual),
                    None,
                )
                if logical is None:
                    continue
                current_visual = header.visualIndex(logical)
                if current_visual != target_visual:
                    header.moveSection(current_visual, target_visual)
        sort_state = state.get("sort")
        if isinstance(sort_state, dict) and int(sort_state.get("column", -1)) == self.COL_ADDR:
            order = Qt.SortOrder.DescendingOrder if sort_state.get("order") == "desc" else Qt.SortOrder.AscendingOrder
            self._sort_rows_by_address(order)

    def _sort_rows_by_address(self, order: Qt.SortOrder) -> None:
        row_snapshots = [self._snapshot_row_data(row) for row in range(self.rowCount())]
        data_rows: list[tuple[tuple[int, int] | None, str, int, list[dict]]] = []
        blank_rows: list[list[dict]] = []

        for index, data in enumerate(row_snapshots):
            if not self._row_has_visible_data(data):
                blank_rows.append(data)
                continue
            address_text = ""
            if self.COL_ADDR < len(data) and data[self.COL_ADDR]:
                address_text = str(data[self.COL_ADDR].get("text", "")).strip()
            parsed = parse_cio_bit(address_text) if address_text else None
            data_rows.append((parsed, address_text.casefold(), index, data))

        valid_rows = [entry for entry in data_rows if entry[0] is not None]
        invalid_rows = [entry for entry in data_rows if entry[0] is None]
        reverse = order == Qt.SortOrder.DescendingOrder

        valid_rows.sort(key=lambda entry: (entry[0][0], entry[0][1], entry[2]), reverse=reverse)
        invalid_rows.sort(key=lambda entry: (entry[1], entry[2]), reverse=reverse)
        ordered_rows = [entry[3] for entry in valid_rows] + [entry[3] for entry in invalid_rows] + blank_rows

        self.blockSignals(True)
        for row, data in enumerate(ordered_rows):
            self._restore_row_data(row, data)
        self.blockSignals(False)
        self.clearSelection()
        self.setCurrentCell(0, self.COL_ADDR)
        self._addr_sort_order = order
        self.horizontalHeader().setSortIndicatorShown(True)
        self.horizontalHeader().setSortIndicator(self.COL_ADDR, order)
        self._after_batch_change("sort_addr", 0)

    def _on_header_section_clicked(self, section: int) -> None:
        if section != self.COL_ADDR:
            return
        next_order = (
            Qt.SortOrder.DescendingOrder
            if self._addr_sort_order == Qt.SortOrder.AscendingOrder
            else Qt.SortOrder.AscendingOrder
        )
        self._sort_rows_by_address(next_order)

    def _apply_cell_edit(self, row: int, col: int, text: str) -> None:
        self._ensure_row_available(row)
        item = self.item(row, col)
        old = item.text() if item else ""
        if old == text:
            return
        self._undo_stack.push(_CellEditCommand(self, row, col, old, text))

    def commit_editor_text(self, row: int, col: int, text: str) -> None:
        self._apply_cell_edit(row, col, text)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        # 清除复制选区的蚂蚁线（因为内容已变）
        self._copied_rect = None
        self._ensure_spare_rows(item.row())
        self.viewport().update()
        self.contentDirty.emit("edit")

    # ── 填充手柄辅助 ──────────────────────────────────────────────────────

    def _selection_rect(self) -> tuple[int, int, int, int] | None:
        """返回 (r0, c0, r1, c1)，若无选区返回 None。"""
        idxs = self.selectedIndexes()
        if not idxs:
            return None
        rows = [i.row() for i in idxs]
        cols = [i.column() for i in idxs]
        return min(rows), min(cols), max(rows), max(cols)

    def _handle_rect(self) -> QRect | None:
        """
        返回当前选区右下角填充手柄的矩形（视口坐标）。
        若无选区或行数为 0 则返回 None。
        """
        sel = self._selection_rect()
        if sel is None:
            return None
        _r0, _c0, r1, c1 = sel
        cell_rect = self.visualRect(self.model().index(r1, c1))
        if cell_rect.isNull():
            return None
        cx = cell_rect.right() - _HANDLE_SIZE // 2
        cy = cell_rect.bottom() - _HANDLE_SIZE // 2
        return QRect(cx - _HANDLE_SIZE // 2, cy - _HANDLE_SIZE // 2, _HANDLE_SIZE, _HANDLE_SIZE)

    def _selection_border_color(self) -> QColor:
        return QColor(_HighlightHeaderView.COL_HEADER_BORDER)

    def _is_over_handle(self, pos: QPoint) -> bool:
        hr = self._handle_rect()
        if hr is None:
            return False
        hit = hr.adjusted(-(_HANDLE_HIT - _HANDLE_SIZE) // 2,
                          -(_HANDLE_HIT - _HANDLE_SIZE) // 2,
                           (_HANDLE_HIT - _HANDLE_SIZE) // 2,
                           (_HANDLE_HIT - _HANDLE_SIZE) // 2)
        return hit.contains(pos)

    # ── 绘制填充手柄和选区边框 ────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        painter = QPainter(self.viewport())

        sel = self._selection_rect()
        if sel is not None:
            r0, c0, r1, c1 = sel
            top_left = self.visualRect(self.model().index(r0, c0))
            bottom_right = self.visualRect(self.model().index(r1, c1))
            if not top_left.isNull() and not bottom_right.isNull():
                selection_rect = top_left.united(bottom_right)
                pen = QPen(self._selection_border_color(), 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(selection_rect.adjusted(0, 0, -1, -1))

        # 绘制填充手柄（小蓝色实心正方形）
        hr = self._handle_rect()
        if hr is not None:
            painter.fillRect(hr, QColor("#2563EB"))

        # 拖拽时绘制预览虚线框（支持纵向和横向）
        if self._fill_dragging and (self._fill_preview_row >= 0 or self._fill_preview_col >= 0):
            if sel is not None:
                r0 = self._fill_sel_r0
                c0 = self._fill_sel_c0
                r1 = self._fill_sel_r1
                c1 = self._fill_sel_c1

                # 纵向预览
                if self._fill_preview_row >= 0:
                    r_end = self._fill_preview_row
                    if r_end != r1:
                        top_cell    = self.visualRect(self.model().index(min(r0, r_end), c0))
                        bottom_cell = self.visualRect(self.model().index(max(r1, r_end), c1))
                        if not top_cell.isNull() and not bottom_cell.isNull():
                            preview_rect = top_cell.united(bottom_cell)
                            pen = QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine)
                            painter.setPen(pen)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawRect(preview_rect.adjusted(1, 1, -1, -1))

                # 横向预览
                if self._fill_preview_col >= 0:
                    c_end = self._fill_preview_col
                    if c_end != c1:
                        left_cell  = self.visualRect(self.model().index(r0, min(c0, c_end)))
                        right_cell = self.visualRect(self.model().index(r1, max(c1, c_end)))
                        if not left_cell.isNull() and not right_cell.isNull():
                            preview_rect = left_cell.united(right_cell)
                            pen = QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine)
                            painter.setPen(pen)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawRect(preview_rect.adjusted(1, 1, -1, -1))

        # 复制选区蚂蚁线（Ctrl+C 后显示虚线边框）
        if self._copied_rect is not None:
            r0, c0, r1, c1 = self._copied_rect
            top_left = self.visualRect(self.model().index(r0, c0))
            bottom_right = self.visualRect(self.model().index(r1, c1))
            if not top_left.isNull() and not bottom_right.isNull():
                rect = top_left.united(bottom_right)
                pen = QPen(QColor("#2563EB"), 2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # 绘制拖拽插入指示器（阶段四：行拖拽排序）
        if self._row_drag_drop_position is not None:
            row = self._row_drag_drop_position
            if 0 <= row <= self.rowCount():
                idx = self.model().index(row - 1, 0) if row > 0 else self.model().index(0, 0)
                if idx.isValid():
                    cell_rect = self.visualRect(idx)
                    # 在行上边缘绘制水平线
                    y_pos = cell_rect.top() if row == 0 else cell_rect.bottom()
                    pen = QPen(QColor("#1E40AF"), 2, Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    painter.drawLine(0, y_pos, self.viewport().width(), y_pos)

        painter.end()

    # ── 鼠标事件（手柄拖拽） ──────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if self._fill_dragging:
            # 拖拽中：根据鼠标位置确定预览行/列
            pos = event.position().toPoint()
            idx = self.indexAt(pos)
            if idx.isValid():
                row = idx.row()
                col = idx.column()
                # 判断拖拽方向（相对于选区）
                dr = row - self._fill_sel_r1
                dc = col - self._fill_sel_c1
                # 取绝对值较大的方向
                if abs(dr) > abs(dc):
                    # 纵向拖拽
                    self._fill_preview_row = row
                    self._fill_preview_col = -1
                elif abs(dc) > abs(dr):
                    # 横向拖拽
                    self._fill_preview_row = -1
                    self._fill_preview_col = col
                else:
                    # 对角线：优先纵向
                    self._fill_preview_row = row
                    self._fill_preview_col = -1
            else:
                # 超出表格范围
                self._fill_preview_row = self.rowCount() - 1
                self._fill_preview_col = self.columnCount() - 1
            self.viewport().update()
            return

        # 非拖拽：更新光标样式
        pos = event.position().toPoint()
        if self._is_over_handle(pos):
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and self._is_over_handle(pos):
            sel = self._selection_rect()
            if sel is not None:
                r0, c0, r1, c1 = sel
                self._fill_dragging = True
                self._fill_sel_r0   = r0
                self._fill_sel_r1   = r1
                self._fill_sel_c0   = c0
                self._fill_sel_c1   = c1
                self._fill_preview_row = r1
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
                self.viewport().update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if self._fill_dragging and event.button() == Qt.MouseButton.LeftButton:
            self._fill_dragging = False
            target_row = self._fill_preview_row
            target_col = self._fill_preview_col
            r0 = self._fill_sel_r0
            r1 = self._fill_sel_r1
            c0 = self._fill_sel_c0
            c1 = self._fill_sel_c1
            self._fill_preview_row = -1
            self._fill_preview_col = -1
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.viewport().update()

            # 根据预览行/列判断填充方向
            if target_row >= 0 and target_row != r1:
                # 纵向填充
                self._do_fill_drag(r0, c0, r1, c1, target_row)
            elif target_col >= 0 and target_col != c1:
                # 横向填充
                self._do_fill_drag(r0, c0, r1, c1, r1, target_col)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _do_fill_drag(
        self,
        src_r0: int, src_c0: int,
        src_r1: int, src_c1: int,
        dst_r1: int,
        dst_c1: int | None = None,
    ) -> None:
        """
        四向拖拽填充（阶段三）：
        - 向下填充：[src_r0..src_r1] x [src_c0..src_c1] → [src_r1+1..dst_r1]
        - 向上填充：[src_r0..src_r1] x [src_c0..src_c1] → [dst_r1..src_r0-1]
        - 向右填充：[src_r0..src_r1] x [src_c0..src_c1] → [src_c1+1..dst_c1]
        - 向左填充：[src_r0..src_r1] x [src_c0..src_c1] → [dst_c1..src_c0-1]

        地址列（COL_ADDR）按欧姆龙规则递增（检测步长），其他列复制最后一行/列的值。
        """
        # 判断拖拽方向
        is_down  = dst_r1 > src_r1
        is_up    = dst_r1 < src_r0
        is_right = dst_c1 is not None and dst_c1 > src_c1
        is_left  = dst_c1 is not None and dst_c1 < src_c0

        changes: list[tuple[int, int, str, str]] = []

        # 计算地址列步长（仅当源区有2+个单元格时）
        addr_step = self._detect_addr_step(src_r0, src_c0, src_r1, src_c1)

        if is_down or is_up:
            # 纵向填充（向下或向上）
            row_start, row_end, row_step = (
                (src_r1 + 1, dst_r1 + 1, 1) if is_down else
                (dst_r1, src_r0, 1)
            )

            for c in range(src_c0, src_c1 + 1):
                source_values = [
                    self.item(r, c).text() if self.item(r, c) else ""
                    for r in range(src_r0, src_r1 + 1)
                ]
                anchor_val = source_values[0] if is_up else source_values[-1]
                text_fill_values = (
                    None
                    if c == self.COL_ADDR
                    else _build_text_fill_values(source_values, row_end - row_start, reverse=is_up)
                )

                # 地址列：从源区起始地址开始计算
                if c == self.COL_ADDR and addr_step is not None:
                    # 使用检测到的步长
                    running_addr = anchor_val
                    if is_up:
                        # 向上填充：从 src_r0 的地址开始，按步长递减
                        # 调整为 src_r0-1 的地址
                        running_addr = _omron_add(anchor_val, -addr_step) if anchor_val else anchor_val
                elif c == self.COL_ADDR:
                    # 无步长检测时，使用默认 +1
                    running_addr = anchor_val

                for offset, r in enumerate(range(row_start, row_end)):
                    if c == self.COL_ADDR and addr_step is not None:
                        delta = addr_step if is_down else -addr_step
                        nxt = _omron_add(running_addr, delta) if running_addr else None
                        fill_val = nxt if nxt else running_addr
                        running_addr = fill_val
                    elif c == self.COL_ADDR:
                        nxt = _next_omron_bit(running_addr) if running_addr else None
                        fill_val = nxt if nxt else running_addr
                        running_addr = fill_val
                    else:
                        fill_val = text_fill_values[offset] if text_fill_values is not None else anchor_val

                    # 若目标行不存在则追加
                    if r >= self.rowCount():
                        self.insertRow(r)
                        for cc in range(self.columnCount()):
                            self.setItem(r, cc, QTableWidgetItem(""))

                    old = (self.item(r, c).text() if self.item(r, c) else "")
                    if old != fill_val:
                        changes.append((r, c, old, fill_val))

        elif is_right or is_left:
            # 横向填充（向右或向左）
            col_start, col_end, col_step = (
                (src_c1 + 1, dst_c1 + 1, 1) if is_right else
                (dst_c1, src_c0, 1)
            )

            for r in range(src_r0, src_r1 + 1):
                source_values = [
                    self.item(r, c).text() if self.item(r, c) else ""
                    for c in range(src_c0, src_c1 + 1)
                ]
                anchor_val = source_values[0] if is_left else source_values[-1]
                text_fill_values = _build_text_fill_values(source_values, col_end - col_start, reverse=is_left)

                for offset, c in enumerate(range(col_start, col_end)):
                    # 横向填充时，地址列也简单复制（不按欧姆龙规则）
                    fill_val = text_fill_values[offset] if text_fill_values is not None else anchor_val

                    old = (self.item(r, c).text() if self.item(r, c) else "")
                    if old != fill_val:
                        changes.append((r, c, old, fill_val))

        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "拖拽填充", "fill_drag"))

    def _detect_addr_step(self, r0: int, c0: int, r1: int, c1: int) -> int | None:
        """
        检测地址列步长（仅当纵向填充且有2+个单元格时）。
        返回步长（如 0.00, 0.02 → 步长 2），无法检测则返回 None。
        """
        # 仅纵向填充时检测步长
        if r1 - r0 < 1 or c0 != c1:
            return None

        # 检查地址列
        c = c0
        if c != self.COL_ADDR:
            return None

        # 收集源区所有地址
        addrs = []
        for r in range(r0, r1 + 1):
            item = self.item(r, c)
            if item:
                addr = item.text()
                if addr:
                    addrs.append(addr)

        # 需要至少2个有效地址才能检测步长
        if len(addrs) < 2:
            return None

        # 解析第一个和最后一个地址，计算步长
        try:
            first_word, first_bit = parse_cio_bit(addrs[0])
            last_word, last_bit = parse_cio_bit(addrs[-1])
            if first_word is None or last_word is None:
                return None

            # 计算总 bit 偏移
            total_offset = (last_word - first_word) * 16 + (last_bit - first_bit)
            if total_offset == 0:
                return None

            # 计算平均步长（向上取整）
            step = total_offset // (len(addrs) - 1)
            return step if step != 0 else None
        except Exception:
            return None

    # ── 键盘事件（模块1+2核心逻辑） ──────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        key  = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        # ── 模块1：编辑交互 ──────────────────────────────────────────────────
        # F2 进入编辑
        if key == Qt.Key.Key_F2:
            idx = self.currentIndex()
            if idx.isValid():
                self.editItem(self.item(idx.row(), idx.column()))
            return

        if alt and key == Qt.Key.Key_Down:
            idx = self.currentIndex()
            if idx.isValid() and idx.column() == self.COL_DTYPE:
                item = self.item(idx.row(), idx.column())
                if item is None:
                    item = QTableWidgetItem("")
                    self.setItem(idx.row(), idx.column(), item)
                self.editItem(item)
                editor = self.focusWidget()
                if isinstance(editor, QComboBox):
                    editor.showPopup()
                return

        # Escape 退出编辑恢复原内容
        if key == Qt.Key.Key_Escape:
            if self.state() == QAbstractItemView.State.EditingState:
                # 恢复原始内容
                orig = self._delegate.get_orig_text()
                if orig is not None:
                    idx = self.currentIndex()
                    if idx.isValid():
                        item = self.item(idx.row(), idx.column())
                        if item:
                            item.setText(orig)
                self.closePersistentEditor(self.currentIndex())
                return

        # 直接打字开始编辑（可打印字符）
        # 排除修饰键和功能键
        if (
            not ctrl and not shift
            and event.text()
            and event.text()[0].isprintable()
            and key not in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab)
        ):
            idx = self.currentIndex()
            if idx.isValid() and self.state() != QAbstractItemView.State.EditingState:
                # 先进入编辑，然后插入输入的字符
                self.editItem(self.item(idx.row(), idx.column()))
                editor = self.focusWidget()
                if isinstance(editor, QLineEdit):
                    editor.clear()
                    editor.insert(event.text())
            else:
                super().keyPressEvent(event)
            return

        # ── 模块2：选区与导航 ──────────────────────────────────────────────
        # Ctrl+A 全选
        if ctrl and key == Qt.Key.Key_A:
            self.selectAll()
            return

        if shift and key == Qt.Key.Key_Space:
            idx = self.currentIndex()
            if idx.isValid():
                self.selectRow(idx.row())
            return

        # Ctrl+Home 跳到 A1
        if ctrl and key == Qt.Key.Key_Home:
            if self.rowCount() > 0 and self.columnCount() > 0:
                self.setCurrentCell(0, 0)
            return

        # Ctrl+End 跳到数据最后一行最后一列
        if ctrl and key == Qt.Key.Key_End:
            if self.rowCount() > 0 and self.columnCount() > 0:
                # 找到最后一行有数据的行
                last_data_row = -1
                for r in range(self.rowCount() - 1, -1, -1):
                    has_data = False
                    for c in range(self.columnCount()):
                        item = self.item(r, c)
                        if item and item.text().strip():
                            has_data = True
                            break
                    if has_data:
                        last_data_row = r
                        break
                if last_data_row >= 0:
                    self.setCurrentCell(last_data_row, self.columnCount() - 1)
            return

        # 方向键扩展选区（Shift+方向键）
        if shift and key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
            idx = self.currentIndex()
            if not idx.isValid():
                super().keyPressEvent(event)
                return
            r, c = idx.row(), idx.column()
            nr, nc = r, c
            if key == Qt.Key.Key_Up:
                nr = max(0, r - 1)
            elif key == Qt.Key.Key_Down:
                nr = min(self.rowCount() - 1, r + 1)
            elif key == Qt.Key.Key_Left:
                nc = max(0, c - 1)
            elif key == Qt.Key.Key_Right:
                nc = min(self.columnCount() - 1, c + 1)
            self.setCurrentCell(nr, nc)
            # Qt 会自动扩展选区
            return

        # Ctrl+方向键跳到数据边缘
        if ctrl and key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
            idx = self.currentIndex()
            if not idx.isValid():
                super().keyPressEvent(event)
                return
            r, c = idx.row(), idx.column()
            nr, nc = r, c
            if key == Qt.Key.Key_Up:
                # 向上找第一个非空单元格
                nr = -1
                for rr in range(r - 1, -1, -1):
                    if self.item(rr, c) and self.item(rr, c).text().strip():
                        nr = rr
                        break
                if nr < 0:
                    nr = 0
            elif key == Qt.Key.Key_Down:
                # 向下找第一个非空单元格
                nr = self.rowCount() - 1
                for rr in range(r + 1, self.rowCount()):
                    if self.item(rr, c) and self.item(rr, c).text().strip():
                        nr = rr
                        break
            elif key == Qt.Key.Key_Left:
                # 向左找第一个非空单元格
                nc = -1
                for cc in range(c - 1, -1, -1):
                    if self.item(r, cc) and self.item(r, cc).text().strip():
                        nc = cc
                        break
                if nc < 0:
                    nc = 0
            elif key == Qt.Key.Key_Right:
                # 向右找第一个非空单元格
                nc = self.columnCount() - 1
                for cc in range(c + 1, self.columnCount()):
                    if self.item(r, cc) and self.item(r, cc).text().strip():
                        nc = cc
                        break
            self.setCurrentCell(nr, nc)
            return

        # Ctrl+Shift+方向键跳到边缘并扩展选区
        if ctrl and shift and key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
            idx = self.currentIndex()
            if not idx.isValid():
                super().keyPressEvent(event)
                return
            r, c = idx.row(), idx.column()
            nr, nc = r, c
            if key == Qt.Key.Key_Up:
                nr = 0
                for rr in range(r - 1, -1, -1):
                    if self.item(rr, c) and self.item(rr, c).text().strip():
                        nr = rr
                        break
            elif key == Qt.Key.Key_Down:
                nr = self.rowCount() - 1
                for rr in range(r + 1, self.rowCount()):
                    if self.item(rr, c) and self.item(rr, c).text().strip():
                        nr = rr
                        break
            elif key == Qt.Key.Key_Left:
                nc = 0
                for cc in range(c - 1, -1, -1):
                    if self.item(r, cc) and self.item(r, cc).text().strip():
                        nc = cc
                        break
            elif key == Qt.Key.Key_Right:
                nc = self.columnCount() - 1
                for cc in range(c + 1, self.columnCount()):
                    if self.item(r, cc) and self.item(r, cc).text().strip():
                        nc = cc
                        break
            self.setCurrentCell(nr, nc)
            return

        # ── 原有快捷键 ──────────────────────────────────────────────────────
        if ctrl and key == Qt.Key.Key_C:
            self._copy_selection(); return
        if ctrl and key == Qt.Key.Key_X:
            self._cut_selection(); return
        if ctrl and key == Qt.Key.Key_V:
            self._paste(); return
        if ctrl and key == Qt.Key.Key_Z:
            self._undo_stack.undo(); return
        if ctrl and key == Qt.Key.Key_Y:
            self._undo_stack.redo(); return
        if ctrl and key == Qt.Key.Key_D:
            self._fill_down(); return
        if ctrl and key == Qt.Key.Key_R:
            self._fill_right(); return

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._clear_selection(); return

        if key == Qt.Key.Key_Tab:
            tab_navigation = str(self._editor_defaults.get("tab_navigation", "right"))
            if tab_navigation == "down":
                self._navigate(-1 if shift else 1, 0)
            else:
                self._navigate(0, -1 if shift else 1)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.isPersistentEditorOpen(self.currentIndex()):
                enter_navigation = str(self._editor_defaults.get("enter_navigation", "down"))
                if enter_navigation == "right":
                    self._navigate(0, -1 if shift else 1)
                else:
                    self._navigate(-1 if shift else 1, 0)
                return

        super().keyPressEvent(event)

    def _navigate(self, dr: int, dc: int) -> None:
        """导航：支持 Tab 行末换行、Enter 记住列"""
        idx = self.currentIndex()
        if not idx.isValid():
            return
        r, c = idx.row(), idx.column()

        # Enter 记住列（首次 Enter 触发时记录列）
        if dr != 0 and dc == 0 and self._enter_column is None:
            self._enter_column = c

        # Enter 使用记住的列，否则使用当前列
        if dr != 0 and dc == 0 and self._enter_column is not None:
            c = self._enter_column

        # Tab 导航
        if dc != 0:
            c += dc
            # Tab 到行末自动换行
            if c >= self.columnCount():
                c = 0
                r += 1
            elif c < 0:
                c = self.columnCount() - 1
                r -= 1

        # Enter 导航
        if dr != 0 and dc == 0:
            r += dr

        if r >= self.rowCount():
            self._ensure_row_available(r)

        # 边界检查
        r = max(0, min(r, self.rowCount() - 1))
        c = max(0, min(c, self.columnCount() - 1))

        if (
            bool(self._editor_defaults.get("continuous_entry"))
            and r > idx.row()
        ):
            self._seed_row_from_previous(idx.row(), r)

        self._ensure_spare_rows(r)
        self.setCurrentCell(r, c)
        self.scrollTo(self.model().index(r, c))

    def _seed_row_from_previous(self, source_row: int, target_row: int) -> None:
        if target_row <= source_row:
            return
        self._ensure_row_available(target_row)
        changes: list[tuple[int, int, str, str]] = []

        def _current_text(row: int, col: int) -> str:
            item = self.item(row, col)
            return item.text() if item else ""

        def _queue_if_blank(col: int, new_value: str) -> None:
            if not new_value:
                return
            old = _current_text(target_row, col)
            if old:
                return
            changes.append((target_row, col, old, new_value))

        if bool(self._editor_defaults.get("inherit_data_type")):
            _queue_if_blank(self.COL_DTYPE, _current_text(source_row, self.COL_DTYPE))
        if bool(self._editor_defaults.get("inherit_rack")):
            _queue_if_blank(self.COL_RACK, _current_text(source_row, self.COL_RACK))
        if bool(self._editor_defaults.get("inherit_usage")):
            _queue_if_blank(self.COL_USAGE, _current_text(source_row, self.COL_USAGE))
        if bool(self._editor_defaults.get("auto_increment_address")):
            source_address = _current_text(source_row, self.COL_ADDR)
            next_address = _next_omron_bit(source_address) if source_address else None
            if next_address:
                _queue_if_blank(self.COL_ADDR, next_address)
        if bool(self._editor_defaults.get("auto_increment_name")):
            source_name = _current_text(source_row, self.COL_NAME)
            next_names = _build_text_fill_values([source_name], 1) if source_name else None
            if next_names:
                _queue_if_blank(self.COL_NAME, next_names[0])
        if bool(self._editor_defaults.get("auto_increment_comment")):
            source_comment = _current_text(source_row, self.COL_COMMENT)
            next_comments = _build_text_fill_values([source_comment], 1) if source_comment else None
            if next_comments:
                _queue_if_blank(self.COL_COMMENT, next_comments[0])
        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "连续录入补全", "continuous_entry"))

    # ── 复制 / 粘贴 / 清除 ────────────────────────────────────────────────

    def _selected_rect(self) -> tuple[int, int, int, int] | None:
        idxs = self.selectedIndexes()
        if not idxs:
            return None
        rows = [i.row() for i in idxs]
        cols = [i.column() for i in idxs]
        return min(rows), min(cols), max(rows), max(cols)

    def _copy_selection(self) -> None:
        rect = self._selected_rect()
        if rect is None:
            return
        r0, c0, r1, c1 = rect
        lines = []
        for r in range(r0, r1 + 1):
            cells = []
            for c in range(c0, c1 + 1):
                item = self.item(r, c)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
        # 记录复制选区，显示蚂蚁线
        self._copied_rect = rect
        self.viewport().update()

    def _cut_selection(self) -> None:
        self._copy_selection()
        self._clear_selection()

    def _paste(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            return
        rows_data = [line.split("\t") for line in text.splitlines()]
        if not rows_data:
            return
        src_cols = max(len(row) for row in rows_data)
        rows_data = [row + [""] * (src_cols - len(row)) for row in rows_data]
        anchor = self.currentIndex()
        if not anchor.isValid():
            return
        selection = self._selected_rect()
        r0, c0 = anchor.row(), anchor.column()
        target_cells: list[tuple[int, int, str]] = []

        if selection is not None:
            sr0, sc0, sr1, sc1 = selection
            target_rows = sr1 - sr0 + 1
            target_cols = sc1 - sc0 + 1
            src_rows = len(rows_data)

            if src_rows == 1 and src_cols == 1 and (target_rows > 1 or target_cols > 1):
                fill = rows_data[0][0]
                for row in range(sr0, sr1 + 1):
                    for col in range(sc0, sc1 + 1):
                        target_cells.append((row, col, fill))
            elif src_rows == 1 and src_cols == target_cols and target_rows > 1:
                for row in range(sr0, sr1 + 1):
                    for offset, value in enumerate(rows_data[0]):
                        target_cells.append((row, sc0 + offset, value))
            elif src_cols == 1 and src_rows == target_rows and target_cols > 1:
                for offset, row_data in enumerate(rows_data):
                    for col in range(sc0, sc1 + 1):
                        target_cells.append((sr0 + offset, col, row_data[0]))
            elif src_rows == target_rows and src_cols == target_cols:
                for row_offset, row_data in enumerate(rows_data):
                    for col_offset, value in enumerate(row_data):
                        target_cells.append((sr0 + row_offset, sc0 + col_offset, value))

        if not target_cells:
            for row_offset, row_data in enumerate(rows_data):
                for col_offset, value in enumerate(row_data):
                    target_cells.append((r0 + row_offset, c0 + col_offset, value))

        max_row = max((row for row, _, _ in target_cells), default=r0)
        self._ensure_row_available(max_row)
        changes: list[tuple[int, int, str, str]] = []
        for row, col, value in target_cells:
            if col >= self.columnCount():
                continue
            old = (self.item(row, col).text() if self.item(row, col) else "")
            if old != value:
                changes.append((row, col, old, value))
        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "粘贴", "paste"))

    def _clear_selection(self) -> None:
        idxs = self.selectedIndexes()
        if not idxs:
            return
        changes: list[tuple[int, int, str, str]] = []
        for idx in idxs:
            r, c = idx.row(), idx.column()
            item = self.item(r, c)
            old = item.text() if item else ""
            if old:
                changes.append((r, c, old, ""))
        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "清除", "clear"))

    # ── Ctrl+D 向下填充 ──────────────────────────────────────────────────

    def _fill_down(self) -> None:
        """
        Ctrl+D：用选区第一行填充后续行；
        地址列（COL_ADDR）使用欧姆龙递增规则。
        """
        rect = self._selected_rect()
        if rect is None:
            return
        r0, c0, r1, c1 = rect
        if r1 <= r0:
            return

        changes: list[tuple[int, int, str, str]] = []
        for c in range(c0, c1 + 1):
            first_item = self.item(r0, c)
            first_val  = first_item.text() if first_item else ""
            last_addr  = first_val if c == self.COL_ADDR else None
            text_fill_values = (
                None if c == self.COL_ADDR else _build_text_fill_values([first_val], r1 - r0)
            )

            for offset, r in enumerate(range(r0 + 1, r1 + 1)):
                if c == self.COL_ADDR:
                    if last_addr is not None:
                        nxt = _next_omron_bit(last_addr)
                        fill_val = nxt if nxt else last_addr
                        last_addr = fill_val
                    else:
                        fill_val = first_val
                else:
                    fill_val = text_fill_values[offset] if text_fill_values is not None else first_val

                old = (self.item(r, c).text() if self.item(r, c) else "")
                if old != fill_val:
                    changes.append((r, c, old, fill_val))

        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "向下填充", "fill_down"))

    # ── Ctrl+R 向右填充 ──────────────────────────────────────────────────

    def _fill_right(self) -> None:
        """
        Ctrl+R：用选区第一列填充后续列；
        地址列（COL_ADDR）使用欧姆龙递增规则（如果从地址列开始）。
        """
        rect = self._selected_rect()
        if rect is None:
            return
        r0, c0, r1, c1 = rect
        if c1 <= c0:
            return

        changes: list[tuple[int, int, str, str]] = []
        for r in range(r0, r1 + 1):
            first_item = self.item(r, c0)
            first_val  = first_item.text() if first_item else ""
            last_addr  = first_val if c0 == self.COL_ADDR else None
            text_fill_values = _build_text_fill_values([first_val], c1 - c0)

            for offset, c in enumerate(range(c0 + 1, c1 + 1)):
                if c == self.COL_ADDR and last_addr is not None:
                    nxt = _next_omron_bit(last_addr)
                    fill_val = nxt if nxt else last_addr
                    last_addr = fill_val
                else:
                    fill_val = text_fill_values[offset] if text_fill_values is not None else first_val

                old = (self.item(r, c).text() if self.item(r, c) else "")
                if old != fill_val:
                    changes.append((r, c, old, fill_val))

        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "向右填充", "fill_right"))

    # ── 右键菜单 ────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:  # noqa: ANN001
        menu = QMenu(self)

        # 插入/删除行
        act_insert_above = menu.addAction("⬆ 在上方插入行")
        act_insert_below = menu.addAction("⬇ 在下方插入行")
        menu.addSeparator()

        # 复制/剪切/粘贴/清除
        act_copy  = menu.addAction("复制      Ctrl+C")
        act_cut   = menu.addAction("剪切      Ctrl+X")
        act_paste = menu.addAction("粘贴      Ctrl+V")
        act_clear = menu.addAction("清除      Delete")
        menu.addSeparator()

        # 填充
        act_fill_down = menu.addAction("向下填充  Ctrl+D")
        act_fill_right = menu.addAction("向右填充  Ctrl+R")
        act_fill_addr = menu.addAction("向下填充地址（欧姆龙）")
        menu.addSeparator()

        # 删除行
        act_del_row = menu.addAction("🗑 删除选中行")

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_insert_above:
            self._insert_row(below=False)
        elif chosen == act_insert_below:
            self._insert_row(below=True)
        elif chosen == act_copy:
            self._copy_selection()
        elif chosen == act_cut:
            self._cut_selection()
        elif chosen == act_paste:
            self._paste()
        elif chosen == act_clear:
            self._clear_selection()
        elif chosen == act_fill_down:
            self._fill_down()
        elif chosen == act_fill_right:
            self._fill_right()
        elif chosen == act_fill_addr:
            self._fill_addr_from_selection()
        elif chosen == act_del_row:
            self._delete_selected_rows()

    def _insert_row(self, below: bool = True) -> None:
        idx = self.currentIndex()
        r = idx.row() if idx.isValid() else self.rowCount() - 1
        insert_at = r + 1 if below else r
        self.blockSignals(True)
        self.insertRow(insert_at)
        for c in range(self.columnCount()):
            self.setItem(insert_at, c, QTableWidgetItem(""))
        self.blockSignals(False)
        self._after_batch_change("insert_row", insert_at)

    def _delete_selected_rows(self) -> None:
        rows = sorted({i.row() for i in self.selectedIndexes()}, reverse=True)
        self.blockSignals(True)
        for r in rows:
            self.removeRow(r)
        self.blockSignals(False)
        if rows:
            self._after_batch_change("delete_rows", min(rows))

    def _fill_addr_from_selection(self) -> None:
        """从选区第一个地址列单元格开始向下填充欧姆龙地址。"""
        rect = self._selected_rect()
        if rect is None:
            return
        r0, c0, r1, c1 = rect
        addr_col = self.COL_ADDR
        first_item = self.item(r0, addr_col)
        first_val  = first_item.text() if first_item else ""
        last_addr: str | None = first_val

        changes: list[tuple[int, int, str, str]] = []
        for r in range(r0 + 1, r1 + 1):
            if last_addr is not None:
                nxt = _next_omron_bit(last_addr)
                fill_val = nxt if nxt else last_addr
                last_addr = fill_val
            else:
                fill_val = ""
            old = (self.item(r, addr_col).text() if self.item(r, addr_col) else "")
            if old != fill_val:
                changes.append((r, addr_col, old, fill_val))
        if changes:
            self._undo_stack.push(_MultiCellCommand(self, changes, "地址填充", "fill_addr"))

    # ── 智能名称补全（委托在编辑开始时触发） ─────────────────────────────

    def get_name_suggestion(self, current_text: str) -> str | None:
        all_names = _all_names_in_table(self, self.COL_NAME)
        if not current_text:
            return None
        return _predict_name(all_names, current_text)

    # ── 行拖拽排序（阶段四） ───────────────────────────────────────────────

    def startDrag(self, supportedActions) -> None:  # noqa: ANN001
        """重写 startDrag，支持行拖拽排序"""
        # 简化：直接使用当前索引作为拖拽起点
        idx = self.currentIndex()
        if not idx.isValid():
            return

        self._row_drag_start_index = idx

        # 调用父类方法
        super().startDrag(supportedActions)

    def dragEnterEvent(self, event) -> None:  # noqa: ANN001
        """拖拽进入事件"""
        if event.source() == self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: ANN001
        """拖拽移动事件，显示插入位置指示器"""
        if event.source() == self:
            # 根据鼠标位置计算插入行
            pos = event.position().toPoint()
            idx = self.indexAt(pos)
            if idx.isValid():
                row = idx.row()
                # 根据鼠标在单元格中的上下半部分决定插入位置
                cell_rect = self.visualRect(idx)
                if pos.y() < cell_rect.top() + cell_rect.height() // 2:
                    self._row_drag_drop_position = row
                else:
                    self._row_drag_drop_position = row + 1
                self.viewport().update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: ANN001
        """拖拽放下事件，执行行排序"""
        if event.source() == self and self._row_drag_start_index is not None:
            start_row = self._row_drag_start_index.row()
            drop_pos = self._row_drag_drop_position

            # 重置状态
            self._row_drag_start_index = None
            self._row_drag_drop_position = None
            self.viewport().update()

            # 避免无效操作
            if drop_pos is None or start_row == drop_pos or start_row + 1 == drop_pos:
                event.acceptProposedAction()
                return

            # 执行行移动（使用 UndoCommand）
            self._move_rows([start_row], drop_pos)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ── 行操作辅助（阶段四） ───────────────────────────────────────────────

    def _move_rows(self, rows: list[int], target_row: int) -> None:
        """移动行到目标位置（支持 Undo）"""
        if not rows:
            return

        # 收集所有行数据
        row_data = [self._snapshot_row_data(row) for row in rows]

        # 创建撤销命令
        cmd = _MoveRowsCommand(self, rows, target_row, row_data)
        self._undo_stack.push(cmd)
