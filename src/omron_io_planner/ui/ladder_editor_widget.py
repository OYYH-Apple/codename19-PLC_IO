# -*- coding: utf-8 -*-
"""欧姆龙 v2 梯形图编辑（梯级 + 指令列表，非旧版单元格网格）。"""
from __future__ import annotations

import copy
import uuid

from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import QKeySequence, QShortcut, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..omron_ladder_migration import legacy_kind_to_spec_id, migrate_ladder_network_to_v2, spec_id_to_legacy_kind
from ..omron_ladder_spec import SPEC_BY_ID, validate_instruction_placement
from ..omron_ladder_topology import validate_rung_parallel_topology
from ..program_models import (
    LadderElement,
    LadderInstructionInstance,
    LadderNetwork,
    LadderRung,
    ProgramUnit,
    default_ladder_network_v2,
)
from ..program_symbols import ProgramSymbolIndex, SuggestionItem
from .ladder_graphics_scene import LadderGraphicsScene, LadderGraphicsView
from .ladder_instruction_palette import InstructionDragTree, SymbolDragList


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


def _normalize_ladder_editor_network(network: LadderNetwork) -> None:
    if network.format_version < 2 and network.cells:
        migrate_ladder_network_to_v2(network)
    elif network.format_version >= 2 and not network.rungs:
        network.rungs = [LadderRung(index=i) for i in range(max(network.rows, 1))]


class LadderEditorWidget(QWidget):
    modified = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._symbol_index: ProgramSymbolIndex | None = None
        self._function_block = None
        self._program_unit: ProgramUnit | None = None
        self._undo_stack = QUndoStack(self)
        self._networks = [default_ladder_network_v2(title="网络 1", n_rungs=6)]
        self._applying = False
        self._clipboard_element: LadderElement | None = None
        self._graphics_selected: tuple[str, int, int] = ("", -1, -1)  # instance_id, rung_index, slot_index

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._title_label = QLabel("梯形图（欧姆龙 v2 · 按梯级编辑）")
        self._title_label.setStyleSheet("font-weight: 700; color: #244C7B;")
        root.addWidget(self._title_label)

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
        self._operand_edit.returnPressed.connect(self._apply_operand_to_selection)
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

        outer = QSplitter(Qt.Orientation.Horizontal, self)
        self._network_list = QListWidget(outer)
        self._network_list.currentRowChanged.connect(self._on_network_row_changed)

        palette_tabs = QTabWidget(outer)
        palette_tabs.setMaximumWidth(300)
        self._instruction_palette = InstructionDragTree(palette_tabs)
        self._symbol_drag_list = SymbolDragList(palette_tabs)
        palette_tabs.addTab(self._instruction_palette, "指令")
        palette_tabs.addTab(self._symbol_drag_list, "符号")

        main_split = QSplitter(Qt.Orientation.Horizontal, outer)
        main_split.addWidget(palette_tabs)
        right = QWidget(main_split)
        right_lo = QVBoxLayout(right)
        right_lo.setContentsMargins(0, 0, 0, 0)
        right_lo.setSpacing(6)
        self._rung_list = QListWidget(right)
        self._rung_list.currentRowChanged.connect(self._on_rung_row_changed)
        right_lo.addWidget(QLabel("梯级", right), 0)
        right_lo.addWidget(self._rung_list, 0)

        self._ladder_scene = LadderGraphicsScene(self)
        self._ladder_view = LadderGraphicsView(self._ladder_scene, right)
        self._ladder_view.setMinimumHeight(200)
        self._ladder_view.setToolTip(
            "左侧「指令」树拖到画布槽位即可放置；「符号」列表拖到母线空白建 LD，拖到图元上则写入操作数。\n"
            "单击母线空白可选定放置槽位（橙虚线框）。\n"
            "Ctrl+滚轮：缩放画布  ·  Ctrl+0：复位缩放"
        )
        self._ladder_scene.selection_info_changed.connect(self._on_graphics_selection_changed)
        self._ladder_view.navigate_horizontal.connect(self._ladder_scene.move_selection_horizontal)
        self._ladder_view.navigate_vertical.connect(self._ladder_scene.move_selection_vertical)
        self._ladder_view.delete_selected.connect(self._delete_graphics_selection)
        self._ladder_view.spec_id_dropped_on_canvas.connect(self._on_canvas_spec_drop)
        self._ladder_view.symbol_dropped_on_canvas.connect(self._on_canvas_symbol_drop)

        self._instr_table = QTableWidget(0, 5, right)
        self._instr_table.setHorizontalHeaderLabels(["槽", "指令", "操作数1", "操作数2", "注释"])
        self._instr_table.verticalHeader().setVisible(False)
        self._instr_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._instr_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._instr_table.itemChanged.connect(self._on_instruction_item_changed)
        self._instr_table.currentCellChanged.connect(self._sync_operand_from_instruction_table)

        self._editor_tabs = QTabWidget(right)
        self._editor_tabs.addTab(self._ladder_view, "梯形图")
        self._editor_tabs.addTab(self._instr_table, "指令表")
        self._editor_tabs.setCurrentIndex(1)
        right_lo.addWidget(self._editor_tabs, 1)

        main_split.addWidget(right)
        main_split.setStretchFactor(1, 1)
        outer.addWidget(self._network_list)
        outer.addWidget(main_split)
        outer.setStretchFactor(1, 1)
        root.addWidget(outer, 1)

        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self._instr_table)
        self._copy_shortcut.activated.connect(self.copy_current_cell)
        self._paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self._instr_table)
        self._paste_shortcut.activated.connect(self.paste_current_cell)
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._instr_table)
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
        base = "梯形图（欧姆龙 v2 · 按梯级编辑）"
        if function_block is not None:
            self._title_label.setText(f"{base} — {function_block.name}")
        elif program_unit is not None:
            self._title_label.setText(f"{base} — {program_unit.name}")
        else:
            self._title_label.setText(base)
        names = symbol_index.ladder_operand_names(function_block=function_block, program_unit=program_unit)
        self._symbol_drag_list.set_symbol_names(names)

    def set_networks(self, networks: list[LadderNetwork]) -> None:
        self._apply_networks(networks or [default_ladder_network_v2(title="网络 1", n_rungs=6)])

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
        after.append(default_ladder_network_v2(title=f"网络 {len(after) + 1}", n_rungs=6))
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

    def place_instruction_at(
        self,
        rung_index: int,
        slot_index: int,
        spec_id: str,
        *,
        operand: str = "",
        params: list[str] | None = None,
    ) -> None:
        if spec_id not in SPEC_BY_ID:
            return
        before = self.networks()
        after = self.networks()
        network_index = self._network_list.currentRow()
        network_index = network_index if network_index >= 0 else 0
        while network_index >= len(after):
            after.append(default_ladder_network_v2(title=f"网络 {len(after) + 1}", n_rungs=6))
        network = after[network_index]
        _normalize_ladder_editor_network(network)
        while rung_index >= len(network.rungs):
            network.rungs.append(LadderRung(index=len(network.rungs)))
        rung = network.rungs[rung_index]
        slot_specs = [(e.slot_index, e.spec_id) for e in rung.elements]
        ok_place, err_msg = validate_instruction_placement(
            existing_slot_specs=slot_specs,
            target_slot=int(slot_index),
            new_spec_id=spec_id,
        )
        if not ok_place:
            QMessageBox.warning(self, "无法放置", err_msg)
            return
        spec = SPEC_BY_ID[spec_id]
        nslots = len(spec.operand_slots)
        operand_s = operand.strip()
        if spec_id == "omron.fblk":
            ops = [operand_s, ",".join(params or [])]
        elif spec.parallel_branch_role == "open":
            if not operand_s:
                operand_s = f"P{uuid.uuid4().hex[:6]}"
            ops = [operand_s] if nslots >= 1 else []
        elif spec.parallel_branch_role == "close":
            if not operand_s:
                QMessageBox.warning(
                    self,
                    "无法放置",
                    "闭合并联请先在操作数栏填写分支组名（须与对应「开分支」一致）。",
                )
                return
            ops = [operand_s] if nslots >= 1 else []
        else:
            ops = [operand_s] if nslots >= 1 else []
        while len(ops) < nslots:
            ops.append("")
        branch_gid = ""
        if spec.parallel_branch_role is not None:
            branch_gid = (ops[0] if ops else "").strip()
        inst = LadderInstructionInstance(
            instance_id=str(uuid.uuid4()),
            spec_id=spec_id,
            operands=ops[:nslots],
            slot_index=int(slot_index),
            branch_group_id=branch_gid,
        )
        trial_elements = [e for e in rung.elements if e.slot_index != slot_index] + [inst]
        trial_elements.sort(key=lambda e: e.slot_index)
        topo_errors = validate_rung_parallel_topology(trial_elements)
        if topo_errors:
            QMessageBox.warning(self, "并联拓扑", "\n".join(topo_errors))
            return
        rung.elements = trial_elements
        self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "放置梯形图元件"))

    def place_element(self, row: int, column: int, kind: str, *, operand: str = "", params: list[str] | None = None) -> None:
        spec_id = legacy_kind_to_spec_id(kind)
        if spec_id is None and kind == "box":
            spec_id = "omron.fblk"
        elif spec_id is None:
            return
        self.place_instruction_at(row, column, spec_id, operand=operand, params=params)

    def _on_canvas_spec_drop(self, rung_index: int, slot_index: int, spec_id: str) -> None:
        self._editor_tabs.setCurrentIndex(0)
        self.place_instruction_at(
            rung_index,
            slot_index,
            spec_id,
            operand=self._operand_edit.text().strip(),
        )

    def _on_canvas_symbol_drop(self, symbol: str, target_instance_id: str, rung_index: int, slot_index: int) -> None:
        self._editor_tabs.setCurrentIndex(0)
        if target_instance_id:
            self._apply_symbol_to_instruction(target_instance_id, symbol)
            return
        self.place_instruction_at(rung_index, slot_index, "omron.ld", operand=symbol)

    def _apply_symbol_to_instruction(self, instance_id: str, symbol: str) -> None:
        nw = self._network_list.currentRow()
        if nw < 0 or nw >= len(self._networks):
            return
        before = self.networks()
        after = self.networks()
        net = after[nw]
        for rung in net.rungs:
            inst = self._find_instruction(rung, instance_id)
            if inst is None or inst.spec_id not in SPEC_BY_ID:
                continue
            nslots = len(SPEC_BY_ID[inst.spec_id].operand_slots)
            new_ops = list(inst.operands[:nslots]) if inst.operands else []
            while len(new_ops) < nslots:
                new_ops.append("")
            if nslots >= 1:
                new_ops[0] = symbol.strip()
            inst.operands = new_ops[:nslots]
            self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "拖放绑定操作数"))
            return

    def delete_current_cell(self, row: int | None = None, column: int | None = None) -> None:
        network_index = self._network_list.currentRow()
        rung_index, slot_index = self._resolve_rung_slot(row, column)
        if network_index < 0 or rung_index < 0 or slot_index < 0:
            return
        before = self.networks()
        after = self.networks()
        network = after[network_index]
        if rung_index >= len(network.rungs):
            return
        rung = network.rungs[rung_index]
        new_elements = [e for e in rung.elements if e.slot_index != slot_index]
        if len(new_elements) == len(rung.elements):
            return
        rung.elements = new_elements
        self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "删除梯形图元件"))

    def copy_current_cell(self, row: int | None = None, column: int | None = None) -> None:
        inst = self._instruction_at(*self._resolve_rung_slot(row, column))
        if inst is None:
            return
        legacy = self._instruction_to_legacy_element(inst)
        if legacy is not None:
            self._clipboard_element = copy.deepcopy(legacy)

    def paste_current_cell(self, row: int | None = None, column: int | None = None) -> None:
        if self._clipboard_element is None:
            return
        rung_index, slot_index = self._resolve_rung_slot(row, column)
        rung_index = max(0, rung_index)
        slot_index = max(0, slot_index)
        self.place_element(
            rung_index,
            slot_index,
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
        self._networks = copy.deepcopy(networks or [default_ladder_network_v2(title="网络 1")])
        for network in self._networks:
            _normalize_ladder_editor_network(network)
        self._network_list.blockSignals(True)
        self._network_list.clear()
        for index, network in enumerate(self._networks, start=1):
            self._network_list.addItem(network.title or f"网络 {index}")
        self._network_list.blockSignals(False)
        self._network_list.setCurrentRow(0 if self._networks else -1)
        self._on_network_row_changed(0 if self._networks else -1)
        self._applying = False
        self._sync_ladder_graphics()
        self.modified.emit()

    def _on_network_row_changed(self, row: int) -> None:
        self._ladder_scene.discard_pending_slot()
        if self._applying or row < 0 or row >= len(self._networks):
            self._rung_list.clear()
            self._instr_table.setRowCount(0)
            self._sync_ladder_graphics()
            return
        network = self._networks[row]
        self._rung_list.blockSignals(True)
        self._rung_list.clear()
        for i in range(len(network.rungs)):
            self._rung_list.addItem(f"梯级 {i}")
        self._rung_list.blockSignals(False)
        self._rung_list.setCurrentRow(0 if network.rungs else -1)
        self._on_rung_row_changed(self._rung_list.currentRow())

    def _on_rung_row_changed(self, row: int) -> None:
        self._refresh_instruction_table()
        self._sync_ladder_graphics()

    def _refresh_instruction_table(self) -> None:
        nw_row = self._network_list.currentRow()
        rg_row = self._rung_list.currentRow()
        self._instr_table.blockSignals(True)
        self._instr_table.setRowCount(0)
        if nw_row < 0 or rg_row < 0 or nw_row >= len(self._networks):
            self._instr_table.blockSignals(False)
            return
        network = self._networks[nw_row]
        if rg_row < 0 or rg_row >= len(network.rungs):
            self._instr_table.blockSignals(False)
            return
        rung = network.rungs[rg_row]
        ordered = sorted(rung.elements, key=lambda e: (e.slot_index, e.spec_id))
        self._instr_table.setRowCount(len(ordered))
        for r, inst in enumerate(ordered):
            spec = SPEC_BY_ID.get(inst.spec_id)
            mnem = inst.spec_id if spec is None else spec.mnemonic
            op0 = inst.operands[0] if inst.operands else ""
            op1 = inst.operands[1] if len(inst.operands) > 1 else ""
            for col, text in enumerate([str(inst.slot_index), mnem, op0, op1, inst.comment]):
                item = QTableWidgetItem(text)
                if col in (0, 1):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                else:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._instr_table.setItem(r, col, item)
            id_item = self._instr_table.item(r, 0)
            if id_item is not None:
                id_item.setData(Qt.ItemDataRole.UserRole, inst.instance_id)
        self._instr_table.blockSignals(False)
        self._sync_operand_from_instruction_table(self._instr_table.currentRow(), 0, -1, -1)

    def _on_instruction_item_changed(self, item: QTableWidgetItem) -> None:
        if self._applying:
            return
        row = item.row()
        col = item.column()
        if col in (0, 1):
            return
        id_item = self._instr_table.item(row, 0)
        if id_item is None:
            return
        iid = str(id_item.data(Qt.ItemDataRole.UserRole) or "")
        if not iid:
            return
        before = self.networks()
        after = self.networks()
        nw = self._network_list.currentRow()
        rg = self._rung_list.currentRow()
        if nw < 0 or rg < 0:
            return
        inst = self._find_instruction(after[nw].rungs[rg], iid)
        if inst is None or inst.spec_id not in SPEC_BY_ID:
            return
        nslots = len(SPEC_BY_ID[inst.spec_id].operand_slots)
        op0 = self._instr_table.item(row, 2)
        op1 = self._instr_table.item(row, 3)
        cm = self._instr_table.item(row, 4)
        new_ops = [(op0.text() if op0 else ""), (op1.text() if op1 else "")]
        while len(new_ops) < nslots:
            new_ops.append("")
        inst.operands = new_ops[:nslots]
        inst.comment = (cm.text() if cm else "").strip()
        self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "编辑梯形图指令"))

    def _refresh_operand_completions(self, text: str) -> None:
        self._operand_model.setStringList([item.text for item in self.completion_items(text)])

    def create_operand_symbol(self) -> None:
        operand = self._operand_edit.text().strip()
        if not operand:
            return
        self.create_missing_symbol(operand)

    def _active_rung_index(self) -> int:
        if self._editor_tabs.currentIndex() == 0:
            _iid, ri, _si = self._graphics_selected
            if ri >= 0:
                return ri
        return max(0, self._rung_list.currentRow())

    def _place_at_current_cell(self, kind: str) -> None:
        nw = max(0, self._network_list.currentRow())
        pending = self._ladder_scene.take_pending_slot()
        if pending is not None:
            rung_i, slot = pending
        else:
            rung_i = self._active_rung_index()
            slot = self._infer_place_slot(self._networks[nw].rungs[rung_i])
        self.place_element(rung_i, slot, kind, operand=self._operand_edit.text().strip())

    def _infer_place_slot(self, rung: LadderRung) -> int:
        r = self._instr_table.currentRow()
        ordered = sorted(rung.elements, key=lambda e: (e.slot_index, e.spec_id))
        if 0 <= r < len(ordered):
            return ordered[r].slot_index
        return max((e.slot_index for e in rung.elements), default=-1) + 1

    def _instruction_to_legacy_element(self, inst: LadderInstructionInstance) -> LadderElement | None:
        kind = spec_id_to_legacy_kind(inst.spec_id)
        if kind is None:
            return None
        if kind == "box":
            op0 = inst.operands[0] if inst.operands else ""
            p1 = inst.operands[1] if len(inst.operands) > 1 else ""
            params = [s.strip() for s in p1.split(",") if s.strip()] if p1 else []
            return LadderElement(kind="box", operand=op0, params=params, comment=inst.comment)
        return LadderElement(
            kind=kind,
            operand=inst.operands[0] if inst.operands else "",
            params=[],
            comment=inst.comment,
        )

    def _find_instruction(self, rung: LadderRung, instance_id: str) -> LadderInstructionInstance | None:
        for element in rung.elements:
            if element.instance_id == instance_id:
                return element
        return None

    def _instruction_at(self, rung_index: int, slot_index: int) -> LadderInstructionInstance | None:
        network_index = self._network_list.currentRow()
        if network_index < 0 or rung_index < 0 or network_index >= len(self._networks):
            return None
        rungs = self._networks[network_index].rungs
        if rung_index >= len(rungs):
            return None
        for element in rungs[rung_index].elements:
            if element.slot_index == slot_index:
                return element
        return None

    def _instruction_id_in_network(self, network: LadderNetwork, instance_id: str) -> bool:
        for rung in network.rungs:
            if any(e.instance_id == instance_id for e in rung.elements):
                return True
        return False

    def _sync_ladder_graphics(self) -> None:
        if self._applying:
            return
        nw = self._network_list.currentRow()
        if nw < 0 or nw >= len(self._networks):
            self._ladder_scene.rebuild(None)
            return
        net = self._networks[nw]
        keep_id = self._graphics_selected[0]
        self._ladder_scene.rebuild(net)
        if keep_id and self._instruction_id_in_network(net, keep_id):
            self._ladder_scene.select_instance(keep_id)

    def _on_graphics_selection_changed(self, instance_id: str, rung_index: int, slot_index: int) -> None:
        self._graphics_selected = (instance_id, rung_index, slot_index)
        if instance_id and rung_index >= 0:
            if self._rung_list.count() > 0:
                self._rung_list.blockSignals(True)
                self._rung_list.setCurrentRow(min(rung_index, self._rung_list.count() - 1))
                self._rung_list.blockSignals(False)
            nw = self._network_list.currentRow()
            if 0 <= nw < len(self._networks) and rung_index < len(self._networks[nw].rungs):
                inst = self._find_instruction(self._networks[nw].rungs[rung_index], instance_id)
                if inst is not None:
                    op0 = inst.operands[0] if inst.operands else ""
                    self._operand_edit.blockSignals(True)
                    self._operand_edit.setText(op0)
                    self._operand_edit.blockSignals(False)
                    self._refresh_operand_completions(op0)
            rect = self._ladder_scene.focus_rect_for_instance(instance_id)
            if rect is not None and not rect.isNull():
                self._ladder_view.ensureVisible(rect, 24, 24)

    def _delete_graphics_selection(self) -> None:
        iid, ri, si = self._graphics_selected
        if not iid or ri < 0 or si < 0:
            return
        self.delete_current_cell(ri, si)

    def _apply_operand_to_selection(self) -> None:
        instance_id = self._graphics_selected[0]
        if not instance_id:
            return
        nw = self._network_list.currentRow()
        rg = self._graphics_selected[1]
        if nw < 0 or rg < 0 or nw >= len(self._networks) or rg >= len(self._networks[nw].rungs):
            return
        before = self.networks()
        after = self.networks()
        inst = self._find_instruction(after[nw].rungs[rg], instance_id)
        if inst is None or inst.spec_id not in SPEC_BY_ID:
            return
        text = self._operand_edit.text().strip()
        nslots = len(SPEC_BY_ID[inst.spec_id].operand_slots)
        new_ops = list(inst.operands[:nslots]) if inst.operands else []
        while len(new_ops) < nslots:
            new_ops.append("")
        if nslots >= 1:
            new_ops[0] = text
        inst.operands = new_ops[:nslots]
        self._undo_stack.push(_LadderSnapshotCommand(self, before, after, "编辑操作数"))

    def _resolve_rung_slot(self, rung_index: int | None, slot_index: int | None) -> tuple[int, int]:
        ri = self._rung_list.currentRow() if rung_index is None else rung_index
        if slot_index is not None:
            return ri, slot_index
        r = self._instr_table.currentRow()
        nw = self._network_list.currentRow()
        if nw < 0 or ri < 0 or r < 0:
            return ri, -1
        network = self._networks[nw]
        if ri >= len(network.rungs):
            return ri, -1
        ordered = sorted(network.rungs[ri].elements, key=lambda e: (e.slot_index, e.spec_id))
        if r >= len(ordered):
            return ri, -1
        return ri, ordered[r].slot_index

    def _sync_operand_from_instruction_table(
        self, current_row: int, _current_column: int, _previous_row: int, _previous_column: int
    ) -> None:
        if current_row < 0:
            return
        op_item = self._instr_table.item(current_row, 2)
        self._operand_edit.setText(op_item.text() if op_item else "")
