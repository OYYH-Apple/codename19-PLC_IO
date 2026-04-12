# -*- coding: utf-8 -*-
from __future__ import annotations

from omron_io_planner.models import IoChannel, IoPoint, IoProject
from omron_io_planner.program_models import FunctionBlock, VariableDecl
from omron_io_planner.program_symbols import ProgramSymbolIndex
from omron_io_planner.ui.program_editors import (
    FunctionBlockVariableEditor,
    LadderEditorWidget,
    StructuredTextEditor,
    _st_block_comment_depth,
    _st_line_needs_semicolon_suffix,
    _st_normalize_line_equals_to_colon_equals,
)


def _program_context() -> tuple[IoProject, FunctionBlock, ProgramSymbolIndex]:
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
                [IoPoint(name="SensorReady", data_type="BOOL", address="0.00", comment="到位")],
                zone_id="CIO",
            )
        ],
        function_blocks=[block],
    )
    return project, block, ProgramSymbolIndex(project)


def test_function_block_variable_editor_supports_editing_and_undo(qtbot) -> None:
    editor = FunctionBlockVariableEditor()
    qtbot.addWidget(editor)
    editor.set_variables([VariableDecl(name="Enable", data_type="BOOL", category="IN")])

    editor.add_variable(category="VAR")
    editor.update_cell(1, editor.COL_NAME, "Step")
    editor.update_cell(1, editor.COL_DTYPE, "INT")

    assert [variable.name for variable in editor.variables()] == ["Enable", "Step"]

    editor.undo()
    assert editor.variables()[1].data_type == "BOOL"

    editor.redo()
    assert editor.variables()[1].data_type == "INT"


def test_st_normalize_line_equals_to_colon_equals() -> None:
    assert _st_normalize_line_equals_to_colon_equals("x = 1") == "x := 1"
    assert _st_normalize_line_equals_to_colon_equals("  Out = TRUE") == "  Out := TRUE"
    assert _st_normalize_line_equals_to_colon_equals("x := 1") is None
    assert _st_normalize_line_equals_to_colon_equals("a <= b") is None
    assert _st_normalize_line_equals_to_colon_equals("a=b=c") is None
    assert _st_normalize_line_equals_to_colon_equals("IF a = b THEN") is None
    assert _st_normalize_line_equals_to_colon_equals("WHILE x = 1 DO") is None


def test_st_line_needs_semicolon_suffix() -> None:
    assert _st_line_needs_semicolon_suffix("x := 1") is True
    assert _st_line_needs_semicolon_suffix("x := 1;") is False
    assert _st_line_needs_semicolon_suffix("IF a THEN") is False
    assert _st_line_needs_semicolon_suffix("CASE x OF") is False
    assert _st_line_needs_semicolon_suffix("10:") is False
    assert _st_line_needs_semicolon_suffix("IF") is False
    assert _st_line_needs_semicolon_suffix("") is False


def test_st_block_comment_depth() -> None:
    assert _st_block_comment_depth("") == 0
    assert _st_block_comment_depth("(* ") == 1
    assert _st_block_comment_depth("(* x *) y") == 0
    assert _st_block_comment_depth("(* (* nested *)") == 1


def test_structured_text_editor_tracks_unknown_identifiers_and_can_create_symbol(qtbot) -> None:
    project, block, index = _program_context()
    editor = StructuredTextEditor()
    qtbot.addWidget(editor)
    editor.set_symbol_index(index, function_block=block)

    editor.set_source("JogRequest := SensorReady AND Enable;")

    assert editor.completion_items("Se")[0].text == "SensorReady"
    assert editor.unknown_identifiers() == ["JogRequest"]

    editor.create_missing_symbol("JogRequest", target="function_block")

    assert block.variables[-1].name == "JogRequest"
    assert editor.unknown_identifiers() == []


def test_ladder_editor_places_elements_and_supports_undo(qtbot) -> None:
    project, block, index = _program_context()
    editor = LadderEditorWidget()
    qtbot.addWidget(editor)
    editor.set_symbol_index(index, function_block=block)

    editor.place_element(1, 1, "contact_no", operand="SensorReady")
    editor.place_element(1, 4, "coil", operand="MotorRun")

    network = editor.networks()[0]
    by_slot = {e.slot_index: e for e in network.rungs[1].elements}
    assert by_slot[1].spec_id == "omron.ld"
    assert by_slot[1].operands[0] == "SensorReady"
    assert by_slot[4].spec_id == "omron.out"
    assert by_slot[4].operands[0] == "MotorRun"
    assert any(item.text == "SET" for item in editor.completion_items("Se"))

    editor.undo()
    assert len(editor.networks()[0].rungs[1].elements) == 1

    editor.redo()
    assert len(editor.networks()[0].rungs[1].elements) == 2

    editor.create_missing_symbol("MotorRun")
    assert block.variables[-1].name == "MotorRun"
    assert any(item.text == "MotorRun" for item in editor.completion_items("Mo"))

    editor.copy_current_cell(1, 1)
    editor.paste_current_cell(2, 1)
    assert any(e.slot_index == 1 and e.spec_id == "omron.ld" for e in editor.networks()[0].rungs[2].elements)

    editor.delete_current_cell(2, 1)
    assert not any(e.slot_index == 1 for e in editor.networks()[0].rungs[2].elements)
