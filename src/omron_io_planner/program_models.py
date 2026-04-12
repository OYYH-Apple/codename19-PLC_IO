# -*- coding: utf-8 -*-
"""程序编辑域模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


VARIABLE_CATEGORIES = ("IN", "OUT", "IN_OUT", "VAR", "VAR_TEMP")


@dataclass
class VariableDecl:
    name: str = ""
    data_type: str = "BOOL"
    category: str = "VAR"
    comment: str = ""
    initial_value: str = ""
    at_address: str = ""
    retain: bool = False

    def __post_init__(self) -> None:
        self.category = str(self.category or "VAR").upper()
        if self.category not in VARIABLE_CATEGORIES:
            self.category = "VAR"
        self.data_type = str(self.data_type or "BOOL").strip() or "BOOL"
        self.at_address = str(self.at_address or "").strip()
        self.retain = bool(self.retain)


@dataclass
class StDocument:
    source: str = ""


@dataclass
class LadderElement:
    kind: str
    operand: str = ""
    params: List[str] = field(default_factory=list)
    comment: str = ""


@dataclass
class LadderCell:
    row: int
    column: int
    element: LadderElement | None = None


@dataclass
class LadderInstructionInstance:
    """欧姆龙语义下的一条梯形图指令（v2 梯级内串联元素；阶段 3 并联分支组标识）。"""

    instance_id: str = ""
    spec_id: str = ""
    operands: List[str] = field(default_factory=list)
    comment: str = ""
    slot_index: int = 0
    branch_group_id: str = ""

    def __post_init__(self) -> None:
        self.spec_id = str(self.spec_id or "").strip()
        self.operands = [str(x) for x in (self.operands or [])]
        self.comment = str(self.comment or "").strip()
        self.branch_group_id = str(self.branch_group_id or "").strip()


@dataclass
class LadderRung:
    index: int = 0
    label: str = ""
    comment: str = ""
    elements: List[LadderInstructionInstance] = field(default_factory=list)


@dataclass
class LadderNetwork:
    title: str = ""
    rows: int = 6
    columns: int = 8
    comment: str = ""
    cells: List[LadderCell] = field(default_factory=list)
    format_version: int = 1
    rungs: List[LadderRung] = field(default_factory=list)


@dataclass
class ProgramUnit:
    uid: str
    name: str
    implementation_language: str = "ladder"
    st_document: StDocument = field(default_factory=StDocument)
    ladder_networks: List[LadderNetwork] = field(default_factory=list)
    local_variables: List[VariableDecl] = field(default_factory=list)
    workspace_state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.implementation_language = (self.implementation_language or "ladder").lower()


@dataclass
class FunctionBlock:
    uid: str
    name: str
    implementation_language: str = "st"
    variables: List[VariableDecl] = field(default_factory=list)
    st_document: StDocument = field(default_factory=StDocument)
    ladder_networks: List[LadderNetwork] = field(default_factory=list)
    workspace_state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.implementation_language = (self.implementation_language or "st").lower()


def default_ladder_network_v2(*, title: str = "网络 1", n_rungs: int = 6, columns: int = 8) -> LadderNetwork:
    """新建空梯形图网络（欧姆龙 v2：仅梯级，无 cells）。"""
    n = max(1, int(n_rungs))
    return LadderNetwork(
        title=title,
        rows=n,
        columns=int(columns) or 8,
        comment="",
        cells=[],
        format_version=2,
        rungs=[LadderRung(index=i, label="", comment="", elements=[]) for i in range(n)],
    )
