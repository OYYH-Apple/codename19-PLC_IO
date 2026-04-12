# -*- coding: utf-8 -*-
"""阶段 2：表驱动指令调色板 + 可拖放符号列表。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem

from ..ladder_drag_mime import SPEC_ID_MIME, SYMBOL_NAME_MIME
from ..omron_ladder_spec import catalog_by_category, category_label_zh


class InstructionDragTree(QTreeWidget):
    """按 category 分组的指令树；拖出 `SPEC_ID_MIME`。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMinimumWidth(160)
        self._populate()

    def _populate(self) -> None:
        self.clear()
        grouped = catalog_by_category()
        for cat in sorted(grouped.keys(), key=str.casefold):
            specs = grouped[cat]
            parent_item = QTreeWidgetItem([category_label_zh(cat)])
            parent_item.setFlags(parent_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.addTopLevelItem(parent_item)
            for spec in specs:
                label = f"{spec.mnemonic}"
                if spec.description_zh:
                    label = f"{spec.mnemonic} — {spec.description_zh}"
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.ItemDataRole.UserRole, spec.spec_id)
                child.setFlags(
                    (child.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsSelectable)
                    & ~Qt.ItemFlag.ItemIsDropEnabled
                )
                parent_item.addChild(child)
        self.expandAll()

    def startDrag(self, supportedActions: Qt.DropAction) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None or item.childCount() > 0:
            return
        spec_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not spec_id:
            return
        sid = str(spec_id)
        mime = QMimeData()
        mime.setData(SPEC_ID_MIME, sid.encode("utf-8"))
        mime.setText(sid)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class SymbolDragList(QListWidget):
    """符号名列表；拖出 `SYMBOL_NAME_MIME` 与 `text/plain`。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMinimumWidth(160)

    def set_symbol_names(self, names: list[str]) -> None:
        self.clear()
        for name in names:
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, name)
            self.addItem(it)

    def startDrag(self, supportedActions: Qt.DropAction) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        name = str(item.data(Qt.ItemDataRole.UserRole) or item.text()).strip()
        if not name:
            return
        mime = QMimeData()
        mime.setData(SYMBOL_NAME_MIME, name.encode("utf-8"))
        mime.setText(name)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
