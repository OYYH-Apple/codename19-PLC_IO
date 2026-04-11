# -*- coding: utf-8 -*-
"""程序编辑工作区。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..export import tsv_from_rows
from ..models import IoProject
from ..program_export import cxr_text_from_ladder_networks, rows_variable_table, st_text_for_export
from ..program_models import FunctionBlock, ProgramUnit, StDocument
from ..program_symbols import ProgramSymbolIndex
from .program_editors import FunctionBlockVariableEditor, LadderEditorWidget, StructuredTextEditor


class ProgramWorkspace(QWidget):
    modified = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._project: IoProject | None = None
        self._symbol_index: ProgramSymbolIndex | None = None
        self._current_item_key = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        tools = QWidget(self)
        tools_layout = QHBoxLayout(tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)
        self._add_program_btn = QPushButton("新增主程序", tools)
        self._add_program_btn.setProperty("compact", "true")
        self._add_fb_btn = QPushButton("新增 FB", tools)
        self._add_fb_btn.setProperty("compact", "true")
        self._toggle_language_btn = QPushButton("切换实现", tools)
        self._toggle_language_btn.setProperty("compact", "true")
        self._export_st_btn = QPushButton("复制 ST", tools)
        self._export_st_btn.setProperty("compact", "true")
        self._export_vars_btn = QPushButton("复制变量表", tools)
        self._export_vars_btn.setProperty("compact", "true")
        self._export_ladder_btn = QPushButton("复制梯形图", tools)
        self._export_ladder_btn.setProperty("compact", "true")
        for button in (
            self._add_program_btn,
            self._add_fb_btn,
            self._toggle_language_btn,
            self._export_st_btn,
            self._export_vars_btn,
            self._export_ladder_btn,
        ):
            tools_layout.addWidget(button, 0)
        tools_layout.addStretch(1)
        root.addWidget(tools, 0)

        splitter = QSplitter(self)
        splitter.setChildrenCollapsible(False)
        self._tree = QTreeWidget(splitter)
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(240)
        self._stack = QStackedWidget(splitter)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._placeholder = QLabel("新增主程序或 FB 后即可开始编辑。", self._stack)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._placeholder)

        self._variable_editor = FunctionBlockVariableEditor(self._stack)
        self._stack.addWidget(self._variable_editor)

        self._st_editor = StructuredTextEditor(self._stack)
        self._stack.addWidget(self._st_editor)

        self._ladder_editor = LadderEditorWidget(self._stack)
        self._stack.addWidget(self._ladder_editor)

        self._tree.currentItemChanged.connect(self._on_current_item_changed)
        self._add_program_btn.clicked.connect(self.add_program)
        self._add_fb_btn.clicked.connect(self.add_function_block)
        self._toggle_language_btn.clicked.connect(self.toggle_current_body_language)
        self._export_st_btn.clicked.connect(self.copy_current_st_export)
        self._export_vars_btn.clicked.connect(self.copy_current_variables_export)
        self._export_ladder_btn.clicked.connect(self.copy_current_ladder_export)
        self._variable_editor.modified.connect(lambda: self.modified.emit())
        self._st_editor.modified.connect(lambda: self.modified.emit())
        self._ladder_editor.modified.connect(lambda: self.modified.emit())

    def set_project(self, project: IoProject) -> None:
        self.commit_to_project()
        self._project = project
        self._symbol_index = ProgramSymbolIndex(project)
        self._rebuild_tree()
        state = dict(project.workspace_state.get("program_workspace") or {})
        self._select_item_by_key(str(state.get("selected_item", "") or ""))

    def current_item_key(self) -> str:
        return self._current_item_key

    def item_labels(self) -> list[str]:
        labels: list[str] = []
        root = self._tree.invisibleRootItem()
        for index in range(root.childCount()):
            parent = root.child(index)
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                labels.append(child.text(0))
                for grandchild_index in range(child.childCount()):
                    labels.append(child.child(grandchild_index).text(0))
        return labels

    def capture_state(self) -> dict[str, object]:
        return {"selected_item": self._current_item_key}

    def commit_to_project(self) -> None:
        if self._project is None:
            return
        key = self._current_item_key
        if not key:
            return
        target = self._resolve_key(key)
        if key.endswith(":variables") and isinstance(target, FunctionBlock):
            target.variables = self._variable_editor.variables()
        elif isinstance(target, (FunctionBlock, ProgramUnit)):
            if target.implementation_language == "st":
                target.st_document.source = self._st_editor.source()
            else:
                target.ladder_networks = self._ladder_editor.networks()
        self._project.workspace_state["program_workspace"] = {"selected_item": self._current_item_key}

    def add_program(self) -> None:
        if self._project is None:
            return
        uid = self._next_uid("main", [program.uid for program in self._project.programs])
        name = f"主程序 {len(self._project.programs) + 1}"
        self._project.programs.append(ProgramUnit(uid=uid, name=name, implementation_language="ladder"))
        self._rebuild_tree()
        self._select_item_by_key(f"program:{uid}:body")
        self.modified.emit()

    def add_function_block(self) -> None:
        if self._project is None:
            return
        uid = self._next_uid("fb", [block.uid for block in self._project.function_blocks])
        name = f"FB_{len(self._project.function_blocks) + 1}"
        self._project.function_blocks.append(FunctionBlock(uid=uid, name=name, implementation_language="st"))
        self._rebuild_tree()
        self._select_item_by_key(f"fb:{uid}:variables")
        self.modified.emit()

    def toggle_current_body_language(self) -> None:
        target = self._resolve_key(self._current_item_key)
        if not isinstance(target, (FunctionBlock, ProgramUnit)):
            return
        self.commit_to_project()
        target.implementation_language = "ladder" if target.implementation_language == "st" else "st"
        self._show_item(target, self._current_item_key)
        self.modified.emit()

    def copy_current_st_export(self) -> None:
        target = self._resolve_key(self._current_item_key)
        if not isinstance(target, (FunctionBlock, ProgramUnit)):
            return
        if target.implementation_language != "st":
            return
        self.commit_to_project()
        text = st_text_for_export(target)  # type: ignore[arg-type]
        QApplication.clipboard().setText(text)

    def copy_current_variables_export(self) -> None:
        target = self._resolve_key(self._current_item_key)
        if not isinstance(target, FunctionBlock):
            return
        self.commit_to_project()
        QApplication.clipboard().setText(tsv_from_rows(rows_variable_table(target.variables)))

    def copy_current_ladder_export(self) -> None:
        target = self._resolve_key(self._current_item_key)
        if not isinstance(target, (FunctionBlock, ProgramUnit)):
            return
        if target.implementation_language != "ladder":
            return
        self.commit_to_project()
        QApplication.clipboard().setText(cxr_text_from_ladder_networks(target.name, target.ladder_networks))

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        if self._project is None:
            self._stack.setCurrentWidget(self._placeholder)
            self._current_item_key = ""
            return

        programs_root = QTreeWidgetItem(["主程序"])
        self._tree.addTopLevelItem(programs_root)
        for program in self._project.programs:
            item = QTreeWidgetItem([program.name])
            item.setData(0, Qt.ItemDataRole.UserRole, f"program:{program.uid}:body")
            programs_root.addChild(item)

        fbs_root = QTreeWidgetItem(["功能块"])
        self._tree.addTopLevelItem(fbs_root)
        for block in self._project.function_blocks:
            block_root = QTreeWidgetItem([block.name])
            fbs_root.addChild(block_root)
            variables_item = QTreeWidgetItem([f"{block.name} / 变量定义"])
            variables_item.setData(0, Qt.ItemDataRole.UserRole, f"fb:{block.uid}:variables")
            block_root.addChild(variables_item)
            body_item = QTreeWidgetItem([f"{block.name} / 程序体"])
            body_item.setData(0, Qt.ItemDataRole.UserRole, f"fb:{block.uid}:body")
            block_root.addChild(body_item)

        self._tree.expandAll()
        self._stack.setCurrentWidget(self._placeholder)
        self._current_item_key = ""

    def _select_item_by_key(self, key: str) -> None:
        if not key:
            first = self._tree.topLevelItem(0)
            if first is not None and first.childCount() > 0:
                self._tree.setCurrentItem(first.child(0))
            return
        item = self._find_item_by_key(key)
        if item is not None:
            self._tree.setCurrentItem(item)
            return
        first = self._tree.topLevelItem(0)
        if first is not None and first.childCount() > 0:
            self._tree.setCurrentItem(first.child(0))

    def _find_item_by_key(self, key: str) -> QTreeWidgetItem | None:
        root = self._tree.invisibleRootItem()
        stack = [root.child(index) for index in range(root.childCount())]
        while stack:
            item = stack.pop(0)
            if str(item.data(0, Qt.ItemDataRole.UserRole) or "") == key:
                return item
            for index in range(item.childCount()):
                stack.append(item.child(index))
        return None

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            self._stack.setCurrentWidget(self._placeholder)
            self._current_item_key = ""
            return
        self.commit_to_project()
        key = str(current.data(0, Qt.ItemDataRole.UserRole) or "")
        self._current_item_key = key
        target = self._resolve_key(key)
        self._show_item(target, key)

    def _show_item(self, target, key: str) -> None:  # noqa: ANN001
        if self._symbol_index is None or target is None:
            self._stack.setCurrentWidget(self._placeholder)
            return
        if key.endswith(":variables") and isinstance(target, FunctionBlock):
            self._variable_editor.set_variables(target.variables)
            self._stack.setCurrentWidget(self._variable_editor)
            return
        if isinstance(target, (FunctionBlock, ProgramUnit)):
            if target.implementation_language == "st":
                self._st_editor.set_symbol_index(
                    self._symbol_index,
                    function_block=target if isinstance(target, FunctionBlock) else None,
                    program_unit=target if isinstance(target, ProgramUnit) else None,
                )
                self._st_editor.set_source(target.st_document.source)
                self._stack.setCurrentWidget(self._st_editor)
            else:
                self._ladder_editor.set_symbol_index(
                    self._symbol_index,
                    function_block=target if isinstance(target, FunctionBlock) else None,
                    program_unit=target if isinstance(target, ProgramUnit) else None,
                )
                self._ladder_editor.set_networks(target.ladder_networks or [self._default_network()])
                self._stack.setCurrentWidget(self._ladder_editor)
            return
        self._stack.setCurrentWidget(self._placeholder)

    def _resolve_key(self, key: str):  # noqa: ANN001
        if self._project is None or not key:
            return None
        parts = key.split(":")
        if len(parts) < 3:
            return None
        category, uid, _view = parts[0], parts[1], parts[2]
        if category == "program":
            return next((program for program in self._project.programs if program.uid == uid), None)
        if category == "fb":
            return next((block for block in self._project.function_blocks if block.uid == uid), None)
        return None

    def _default_network(self) -> LadderNetwork:
        return LadderNetwork(title="网络 1", rows=6, columns=8)

    def _next_uid(self, prefix: str, existing: list[str]) -> str:
        index = len(existing) + 1
        uid = f"{prefix}-{index}"
        while uid in existing:
            index += 1
            uid = f"{prefix}-{index}"
        return uid
