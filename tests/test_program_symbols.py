# -*- coding: utf-8 -*-
from __future__ import annotations

from omron_io_planner.models import IoChannel, IoPoint, IoProject
from omron_io_planner.program_models import FunctionBlock, VariableDecl
from omron_io_planner.program_symbols import ProgramSymbolIndex


def _demo_project() -> tuple[IoProject, FunctionBlock]:
    block = FunctionBlock(
        uid="fb-1",
        name="AxisHome",
        variables=[
            VariableDecl(name="Enable", data_type="BOOL", category="IN"),
            VariableDecl(name="Setpoint", data_type="INT", category="VAR"),
        ],
    )
    project = IoProject(
        channels=[
            IoChannel(
                "CIO 区",
                [
                    IoPoint(name="SensorReady", data_type="BOOL", address="0.00", comment="到位"),
                    IoPoint(name="ServoOn", data_type="BOOL", address="0.01", comment="使能"),
                ],
                zone_id="CIO",
            )
        ],
        function_blocks=[block],
    )
    return project, block


def test_program_symbol_index_merges_io_fb_and_keywords() -> None:
    project, block = _demo_project()
    index = ProgramSymbolIndex(project)

    suggestions = index.suggestions("Se", mode="ladder", function_block=block)

    assert [item.text for item in suggestions[:3]] == ["SensorReady", "ServoOn", "Setpoint"]
    assert any(item.text == "SET" and item.source == "keyword" for item in suggestions)


def test_program_symbol_index_supports_blank_prefix_and_deduplicates_creation() -> None:
    project, block = _demo_project()
    index = ProgramSymbolIndex(project)

    suggestions = index.suggestions("", mode="st", function_block=block)
    existing = index.create_missing_symbol("Enable", target="function_block", function_block=block)

    assert any(item.text == "Enable" for item in suggestions)
    assert sum(1 for variable in block.variables if variable.name == "Enable") == 1
    assert existing is block.variables[0]


def test_program_symbol_index_can_create_missing_symbols_for_fb_or_io() -> None:
    project, block = _demo_project()
    index = ProgramSymbolIndex(project)

    created_fb = index.create_missing_symbol("JogRequest", target="function_block", function_block=block)
    created_io = index.create_missing_symbol("AlarmReset", target="io")

    assert created_fb.name == "JogRequest"
    assert created_fb.category == "VAR"
    assert block.variables[-1].name == "JogRequest"
    assert created_io.name == "AlarmReset"
    assert project.channels[0].points[-1].name == "AlarmReset"
