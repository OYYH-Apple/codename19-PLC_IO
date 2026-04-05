# -*- coding: utf-8 -*-
"""数据类型列：受控下拉选择，选项来自 omron_symbol_types。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QRectF, QPoint
from PySide6.QtGui import QPolygonF, QPainter, QPen, QBrush, QColor, QAction
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QMenu,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
)

from ..omron_symbol_types import combo_items
from .io_table_widget import IoTableWidget, _cell_background_color


class DataTypeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items = combo_items()
        self._popup = None  # 弹出的下拉菜单

    def createEditor(self, parent, option, index):  # noqa: ANN001
        cb = QComboBox(parent)
        cb.addItems(self._items)
        cb.setEditable(False)
        cb.setFrame(False)
        cb.setProperty("_setting_editor_data", False)
        background = _cell_background_color(self.parent() if isinstance(self.parent(), IoTableWidget) else None, index.row())
        cb.setStyleSheet(
            "QComboBox {"
            " border: none;"
            f" background-color: {background};"
            " padding: 0 18px 0 2px;"
            " margin: 0;"
            " color: #1E2235;"
            "}"
            "QComboBox:focus {"
            " border: none;"
            " outline: none;"
            f" background-color: {background};"
            "}"
            "QComboBox::drop-down {"
            " border: none;"
            f" background-color: {background};"
            " width: 18px;"
            "}"
            "QComboBox QAbstractItemView {"
            " border: 1px solid #C8CDD8;"
            "}"
        )
        cb.currentIndexChanged.connect(lambda _idx, editor=cb: self._commit_and_close(editor))
        return cb

    def setEditorData(self, editor, index) -> None:  # noqa: ANN001
        if not isinstance(editor, QComboBox):
            return
        t = index.data(Qt.ItemDataRole.DisplayRole)
        text = (str(t) if t is not None else "").strip() or "BOOL"
        u = text.upper()
        editor.setProperty("_setting_editor_data", True)
        editor.blockSignals(True)
        try:
            self._remove_custom_item(editor)
            found = -1
            for j in range(editor.count()):
                if editor.itemText(j).upper() == u:
                    found = j
                    break
            if found >= 0:
                editor.setCurrentIndex(found)
            else:
                editor.addItem(text)
                custom_index = editor.count() - 1
                editor.setProperty("_custom_item_index", custom_index)
                editor.setCurrentIndex(custom_index)
        finally:
            editor.blockSignals(False)
            editor.setProperty("_setting_editor_data", False)

    def _remove_custom_item(self, editor: QComboBox) -> None:
        custom_index = editor.property("_custom_item_index")
        if isinstance(custom_index, int) and 0 <= custom_index < editor.count():
            editor.removeItem(custom_index)
        editor.setProperty("_custom_item_index", -1)

    def setModelData(self, editor, model, index) -> None:  # noqa: ANN001
        if isinstance(editor, QComboBox):
            text = editor.currentText().strip() or "BOOL"
            table = self.parent()
            if isinstance(table, IoTableWidget):
                table.commit_editor_text(index.row(), index.column(), text)
                return
            model.setData(index, text, Qt.ItemDataRole.EditRole)

    def _commit_and_close(self, editor: QComboBox) -> None:
        if editor.property("_setting_editor_data"):
            return
        table = self.parent()
        if isinstance(table, IoTableWidget):
            if table.state() != QAbstractItemView.State.EditingState:
                return
            if editor.parentWidget() is not table.viewport():
                return
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.SubmitModelCache)

    def paint(self, painter, option, index):  # noqa: ANN001
        """绘制单元格文本和下拉箭头图标"""
        # 先调用父类绘制背景和文本
        super().paint(painter, option, index)

        # 绘制下拉箭头图标（在右侧）
        # 计算箭头区域（最后 16px 宽）
        arrow_rect = option.rect
        arrow_rect.setLeft(arrow_rect.right() - 16)

        # 绘制箭头
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 箭头颜色
        arrow_color = QColor("#4A5070") if option.state & QStyle.StateFlag.State_Enabled else QColor("#A0A8C0")
        painter.setPen(QPen(arrow_color, 1.5))
        painter.setBrush(QBrush(arrow_color))

        # 绘制小三角形（向下箭头）
        center_y = arrow_rect.center().y()
        center_x = arrow_rect.center().x()
        triangle = QPolygonF([
            QPoint(center_x - 4, center_y - 2),
            QPoint(center_x + 4, center_y - 2),
            QPoint(center_x, center_y + 2)
        ])
        painter.drawPolygon(triangle)

        painter.restore()

    def editorEvent(self, event, model, option, index):  # noqa: ANN001
        """处理鼠标事件，支持非编辑模式下点击下拉箭头弹出菜单"""
        if event.type() == event.Type.MouseButtonRelease:
            # 检查是否点击了下拉箭头区域
            arrow_rect = option.rect
            arrow_rect.setLeft(arrow_rect.right() - 16)

            pos = event.position().toPoint()
            if arrow_rect.contains(pos):
                # 创建临时的下拉菜单
                self._show_combo_popup(model, index, option.rect)
                return True

        return super().editorEvent(event, model, option, index)

    def _show_combo_popup(self, model, index, cell_rect):  # noqa: ANN001
        """显示下拉菜单供选择"""
        # 获取当前单元格的位置（在视口坐标系）
        if hasattr(model, 'sourceModel'):
            # 处理代理模型
            table = model.parent()
        else:
            table = model.parent()

        if not hasattr(table, 'viewport'):
            return

        # 获取视口的全局位置
        viewport = table.viewport()
        global_pos = viewport.mapToGlobal(QPoint(0, 0))
        cell_global_pos = global_pos + QPoint(cell_rect.left(), cell_rect.bottom())

        # 创建菜单
        menu = QMenu(table)
        menu.setStyleSheet("QMenu { min-width: 120px; }")

        current_value = index.data(Qt.ItemDataRole.DisplayRole)
        current_text = str(current_value).strip() if current_value else ""

        # 添加选项
        for item in self._items:
            action = QAction(item, menu)
            if item.upper() == current_text.upper():
                action.setChecked(True)
            action.triggered.connect(lambda checked, text=item: self._select_item(model, index, text))
            menu.addAction(action)

        # 显示菜单
        menu.exec(cell_global_pos)

    def _select_item(self, model, index, text):  # noqa: ANN001
        """设置选中值"""
        model.setData(index, text, Qt.ItemDataRole.EditRole)
