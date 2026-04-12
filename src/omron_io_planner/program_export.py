# -*- coding: utf-8 -*-
"""程序域导出。"""
from __future__ import annotations

from .cx_emitter import cxr_text_from_ladder_networks as _cxr_text_from_ladder_networks
from .program_models import LadderNetwork, ProgramUnit, VariableDecl


def rows_variable_table(variables: list[VariableDecl]) -> list[list[str]]:
    rows = [["类别", "名称", "数据类型", "AT", "注释", "初始值", "保留"]]
    for variable in variables:
        rows.append(
            [
                variable.category,
                variable.name,
                variable.data_type,
                variable.at_address,
                variable.comment,
                variable.initial_value,
                "1" if variable.retain else "",
            ]
        )
    return rows


def st_text_for_export(program: ProgramUnit) -> str:
    return program.st_document.source


def cxr_text_from_ladder_networks(program_name: str, networks: list[LadderNetwork]) -> str:
    """CXR 文本；实现位于 `cx_emitter` 单模块。"""
    return _cxr_text_from_ladder_networks(program_name, networks)
