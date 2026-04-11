# -*- coding: utf-8 -*-
"""程序编辑统一符号索引。"""
from __future__ import annotations

from dataclasses import dataclass

from .models import IoPoint, IoProject
from .program_models import FunctionBlock, ProgramUnit, VariableDecl


ST_KEYWORDS = (
    "AND",
    "CASE",
    "ELSE",
    "ELSIF",
    "END_CASE",
    "END_FOR",
    "END_IF",
    "END_REPEAT",
    "END_WHILE",
    "FALSE",
    "FOR",
    "IF",
    "NOT",
    "OR",
    "REPEAT",
    "RETURN",
    "THEN",
    "TO",
    "TRUE",
    "UNTIL",
    "VAR",
    "WHILE",
)

LADDER_KEYWORDS = (
    "BOX",
    "CONTACT_NC",
    "CONTACT_NO",
    "COIL",
    "RESET",
    "SET",
)


@dataclass(frozen=True)
class SuggestionItem:
    text: str
    source: str


class ProgramSymbolIndex:
    def __init__(self, project: IoProject) -> None:
        self._project = project

    def suggestions(
        self,
        prefix: str,
        *,
        mode: str,
        function_block: FunctionBlock | None = None,
        program_unit: ProgramUnit | None = None,
    ) -> list[SuggestionItem]:
        token = prefix.strip()
        lower = token.casefold()
        items: list[SuggestionItem] = []
        seen: set[str] = set()

        def _append(values: list[str], source: str) -> None:
            for value in sorted(values, key=str.casefold):
                folded = value.casefold()
                if not value or folded in seen:
                    continue
                if lower and not folded.startswith(lower):
                    continue
                items.append(SuggestionItem(value, source))
                seen.add(folded)

        _append([point.name for channel in self._project.channels for point in channel.points], "io")
        if function_block is not None:
            _append([variable.name for variable in function_block.variables], "function_block")
        if program_unit is not None:
            _append([variable.name for variable in program_unit.local_variables], "program")
        keywords = LADDER_KEYWORDS if mode.lower() == "ladder" else ST_KEYWORDS
        _append(list(keywords), "keyword")
        return items

    def known_names(
        self,
        *,
        function_block: FunctionBlock | None = None,
        program_unit: ProgramUnit | None = None,
        mode: str = "st",
    ) -> set[str]:
        names = {
            point.name
            for channel in self._project.channels
            for point in channel.points
            if point.name.strip()
        }
        if function_block is not None:
            names.update(variable.name for variable in function_block.variables if variable.name.strip())
        if program_unit is not None:
            names.update(variable.name for variable in program_unit.local_variables if variable.name.strip())
        keywords = LADDER_KEYWORDS if mode.lower() == "ladder" else ST_KEYWORDS
        names.update(keywords)
        return names

    def create_missing_symbol(
        self,
        name: str,
        *,
        target: str,
        function_block: FunctionBlock | None = None,
        data_type: str = "BOOL",
    ) -> VariableDecl | IoPoint:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("symbol name must not be empty")
        if target == "function_block" and function_block is not None:
            for variable in function_block.variables:
                if variable.name.casefold() == clean_name.casefold():
                    return variable
            variable = VariableDecl(name=clean_name, data_type=data_type, category="VAR")
            function_block.variables.append(variable)
            return variable
        for channel in self._project.channels:
            for point in channel.points:
                if point.name.casefold() == clean_name.casefold():
                    return point
        if not self._project.channels:
            self._project._init_default_zones()
        point = IoPoint(name=clean_name, data_type=data_type, address="", comment="")
        self._project.channels[0].points.append(point)
        return point
