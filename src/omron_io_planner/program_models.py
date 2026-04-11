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

    def __post_init__(self) -> None:
        self.category = str(self.category or "VAR").upper()
        if self.category not in VARIABLE_CATEGORIES:
            self.category = "VAR"
        self.data_type = str(self.data_type or "BOOL").strip() or "BOOL"


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
class LadderNetwork:
    title: str = ""
    rows: int = 6
    columns: int = 8
    comment: str = ""
    cells: List[LadderCell] = field(default_factory=list)


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
