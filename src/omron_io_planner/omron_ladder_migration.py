# -*- coding: utf-8 -*-
"""旧版 cells 网格 → 欧姆龙 v2（梯级 + 指令实例）迁移。"""
from __future__ import annotations

import uuid
from typing import Iterable

from .program_models import (
    LadderCell,
    LadderElement,
    LadderInstructionInstance,
    LadderNetwork,
    LadderRung,
)


def legacy_kind_to_spec_id(kind: str) -> str | None:
    k = (kind or "").strip().lower()
    return {
        "contact_no": "omron.ld",
        "contact_nc": "omron.ldnot",
        "coil": "omron.out",
        "set": "omron.set",
        "reset": "omron.rset",
    }.get(k)


def element_to_instruction_instance(element: LadderElement, *, slot_index: int) -> LadderInstructionInstance | None:
    spec_id = legacy_kind_to_spec_id(element.kind)
    if spec_id is None:
        if element.kind == "box":
            name = element.operand.strip()
            rest = ",".join(element.params)
            return LadderInstructionInstance(
                instance_id=str(uuid.uuid4()),
                spec_id="omron.fblk",
                operands=[name, rest],
                comment=element.comment,
                slot_index=slot_index,
            )
        return None
    return LadderInstructionInstance(
        instance_id=str(uuid.uuid4()),
        spec_id=spec_id,
        operands=[element.operand.strip()] if element.operand.strip() else [""],
        comment=element.comment,
        slot_index=slot_index,
    )


def spec_id_to_legacy_kind(spec_id: str) -> str | None:
    return {
        "omron.ld": "contact_no",
        "omron.ldnot": "contact_nc",
        "omron.out": "coil",
        "omron.set": "set",
        "omron.rset": "reset",
        "omron.fblk": "box",
    }.get(spec_id)


def _cells_by_row(cells: Iterable[LadderCell]) -> dict[int, list[LadderCell]]:
    by_row: dict[int, list[LadderCell]] = {}
    for cell in cells:
        by_row.setdefault(cell.row, []).append(cell)
    for row in by_row:
        by_row[row].sort(key=lambda c: c.column)
    return by_row


def migrate_ladder_network_to_v2(network: LadderNetwork) -> LadderNetwork:
    """将 v1（cells）网络转为 v2（rungs）；已处于 v2 且含 rungs 时直接返回。"""
    if network.format_version >= 2 and network.rungs:
        network.cells = []
        return network

    by_row = _cells_by_row(network.cells)
    max_row = max(by_row.keys(), default=-1)
    n_rows = max(network.rows, max_row + 1, 1)
    rungs: list[LadderRung] = []
    for r in range(n_rows):
        elements: list[LadderInstructionInstance] = []
        for cell in by_row.get(r, []):
            if cell.element is None:
                continue
            inst = element_to_instruction_instance(cell.element, slot_index=cell.column)
            if inst is not None:
                elements.append(inst)
        elements.sort(key=lambda i: i.slot_index)
        rungs.append(LadderRung(index=r, label="", comment="", elements=elements))

    network.rungs = rungs
    network.format_version = 2
    network.cells = []
    return network
