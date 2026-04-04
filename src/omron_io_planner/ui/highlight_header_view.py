# -*- coding: utf-8 -*-
"""
自定义表头组件：支持选区高亮。

功能：
- Excel 风格列头/行头高亮（选区范围内的行列头加色）
- 支持 QTableWidget 绑定选区变化
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QItemSelectionModel,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QPalette,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QHeaderView,
    QStyle,
    QStyleOptionHeader,
    QStylePainter,
    QTableWidget,
    QTableWidgetSelectionRange,
)


class _HighlightHeaderView(QHeaderView):
    """
    支持 Excel 风格高亮的表头组件。

    高亮规则：
    - 选中单个单元格时：对应行头和列头高亮
    - 选中整行/整列时：整行/整列的行头/列头高亮
    """

    sectionActivated = Signal(int)

    # 高亮颜色（Excel 风格橙色/灰色）
    ROW_HEADER_HIGHLIGHT = QColor("#FEF3C7")  # 浅橙色
    COL_HEADER_HIGHLIGHT = QColor("#FEF3C7")  # 浅橙色
    ROW_HEADER_BORDER = QColor("#F59E0B")      # 深橙色边框
    COL_HEADER_BORDER = QColor("#F59E0B")      # 深橙色边框

    def __init__(
        self,
        orientation: Qt.Orientation,
        table: QTableWidget,
        parent=None,
    ) -> None:
        super().__init__(orientation, parent)
        self._table = table
        self._highlight_sections: set[int] = set()  # 需要高亮的 section 索引
        self._drag_anchor_section: int | None = None

        # 监听选区变化
        if table.selectionModel():
            table.selectionModel().selectionChanged.connect(self._update_highlight)

        self.setSectionsClickable(True)

    def _update_highlight(self) -> None:
        """根据表格选区更新高亮集合"""
        self._highlight_sections.clear()
        idxs = self._table.selectedIndexes()
        if not idxs:
            self.viewport().update()
            return

        if self.orientation() == Qt.Orientation.Horizontal:
            # 列头：收集选中单元格的所有列
            cols = {i.column() for i in idxs}
            self._highlight_sections = cols
        else:
            # 行头：收集选中单元格的所有行
            rows = {i.row() for i in idxs}
            self._highlight_sections = rows

        self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
        """重写绘制方法，支持高亮"""
        # 先调用默认绘制
        super().paintSection(painter, rect, logical_index)

        # 如果该 section 需要高亮，叠加高亮效果
        if logical_index in self._highlight_sections:
            # 半透明背景
            highlight_color = (
                self.COL_HEADER_HIGHLIGHT
                if self.orientation() == Qt.Orientation.Horizontal
                else self.ROW_HEADER_HIGHLIGHT
            )
            highlight_color.setAlpha(100)
            painter.fillRect(rect, highlight_color)
            # 边框
            pen = QPen(
                (
                    self.COL_HEADER_BORDER
                    if self.orientation() == Qt.Orientation.Horizontal
                    else self.ROW_HEADER_BORDER
                ),
                2,
                Qt.PenStyle.SolidLine,
            )
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def _select_vertical_rows(self, start_row: int, end_row: int, clear: bool = True) -> None:
        if self.orientation() != Qt.Orientation.Vertical:
            return
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        if clear:
            self._table.clearSelection()
        top = min(start_row, end_row)
        bottom = max(start_row, end_row)
        for row in range(top, bottom + 1):
            self._table.setRangeSelected(
                QTableWidgetSelectionRange(row, 0, row, self._table.columnCount() - 1),
                True,
            )
        current_col = self._table.currentColumn()
        if current_col < 0:
            current_col = 0
        selection_model.setCurrentIndex(
            self._table.model().index(end_row, current_col),
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        """重写鼠标点击事件，实现整行选择（仅纵向头）"""
        if self.orientation() == Qt.Orientation.Horizontal and event.button() == Qt.MouseButton.LeftButton:
            logical_index = self.logicalIndexAt(event.position().toPoint())
            if logical_index >= 0:
                self.sectionActivated.emit(logical_index)
        if self.orientation() == Qt.Orientation.Vertical:
            # 获取点击的行号
            pos = event.position().toPoint()
            logical_index = self.logicalIndexAt(pos)

            if logical_index >= 0:
                self._drag_anchor_section = logical_index
                # Ctrl 键：添加到选区
                # Shift 键：扩展选区
                # 否则：单选整行
                mods = event.modifiers()
                ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
                shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

                if shift:
                    # 扩展选区
                    idx = self._table.currentIndex()
                    if idx.isValid():
                        current_row = idx.row()
                        self._select_vertical_rows(current_row, logical_index)
                elif ctrl:
                    selection_model = self._table.selectionModel()
                    if selection_model is not None:
                        selection_model.select(
                            self._table.model().index(logical_index, 0),
                            QItemSelectionModel.SelectionFlag.Toggle | QItemSelectionModel.SelectionFlag.Rows,
                        )
                    current_col = self._table.currentColumn()
                    self._table.setCurrentCell(logical_index, current_col if current_col >= 0 else 0)
                else:
                    # 单选整行
                    self._select_vertical_rows(logical_index, logical_index)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if (
            self.orientation() == Qt.Orientation.Vertical
            and self._drag_anchor_section is not None
            and (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            logical_index = self.logicalIndexAt(event.position().toPoint())
            if logical_index >= 0:
                self._select_vertical_rows(self._drag_anchor_section, logical_index)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        self._drag_anchor_section = None
        super().mouseReleaseEvent(event)
