# -*- coding: utf-8 -*-
from __future__ import annotations

from omron_io_planner.models import IoChannel, IoPoint, IoProject
from omron_io_planner.persistence import load_project_json, save_project_json
from omron_io_planner.program_models import (
    FunctionBlock,
    LadderCell,
    LadderElement,
    LadderInstructionInstance,
    LadderNetwork,
    LadderRung,
    ProgramUnit,
    StDocument,
    VariableDecl,
)


def test_project_json_roundtrip_preserves_program_domain(tmp_path) -> None:
    path = tmp_path / "program-project.json"
    project = IoProject(
        name="demo",
        channels=[
            IoChannel(
                "CIO 区",
                [IoPoint(name="StartPB", data_type="BOOL", address="0.00", comment="启动按钮")],
                zone_id="CIO",
            )
        ],
    )
    project.program_settings = {"default_language": "ladder", "entry_scope": "program_workspace"}
    project.programs = [
        ProgramUnit(
            uid="main-1",
            name="主程序 1",
            implementation_language="ladder",
            st_document=StDocument(source=""),
            ladder_networks=[
                LadderNetwork(
                    title="启动保持",
                    rows=4,
                    columns=6,
                    comment="主回路",
                    cells=[
                        LadderCell(
                            row=1,
                            column=1,
                            element=LadderElement(kind="contact_no", operand="StartPB"),
                        ),
                        LadderCell(
                            row=1,
                            column=4,
                            element=LadderElement(kind="coil", operand="MotorRun"),
                        ),
                    ],
                )
            ],
            workspace_state={"selected_network": 0},
        )
    ]
    project.function_blocks = [
        FunctionBlock(
            uid="fb-1",
            name="AxisHome",
            implementation_language="st",
            variables=[
                VariableDecl(name="Enable", data_type="BOOL", category="IN", comment="启动"),
                VariableDecl(name="Done", data_type="BOOL", category="OUT", comment="完成"),
                VariableDecl(
                    name="Step",
                    data_type="INT",
                    category="VAR",
                    comment="步骤",
                    at_address="D100",
                    retain=True,
                ),
            ],
            st_document=StDocument(source="IF Enable THEN\n    Step := 1;\nEND_IF;"),
            workspace_state={"selected_view": "body"},
        )
    ]
    project.workspace_state = {
        "active_tab": "CIO 区",
        "program_workspace": {
            "mode": "program",
            "selected_item": "fb:fb-1:body",
        },
    }

    save_project_json(project, path)
    loaded = load_project_json(path)

    assert loaded.program_settings["default_language"] == "ladder"
    ladder = loaded.programs[0].ladder_networks[0]
    assert ladder.format_version == 2
    assert ladder.cells == []
    by_slot = {e.slot_index: e for e in ladder.rungs[1].elements}
    assert by_slot[1].spec_id == "omron.ld"
    assert by_slot[1].operands[0] == "StartPB"
    assert by_slot[4].spec_id == "omron.out"
    assert by_slot[4].operands[0] == "MotorRun"
    assert loaded.function_blocks[0].variables[1].category == "OUT"
    assert loaded.function_blocks[0].variables[2].at_address == "D100"
    assert loaded.function_blocks[0].variables[2].retain is True
    assert "Step := 1" in loaded.function_blocks[0].st_document.source
    assert loaded.workspace_state["program_workspace"]["selected_item"] == "fb:fb-1:editor"


def test_branch_group_id_roundtrips_in_json(tmp_path) -> None:
    path = tmp_path / "branch.json"
    project = IoProject(name="b", channels=[])
    rungs = [
        LadderRung(
            index=0,
            elements=[
                LadderInstructionInstance(
                    instance_id="i1",
                    spec_id="omron.parallel_open",
                    operands=["G1"],
                    slot_index=0,
                    branch_group_id="G1",
                ),
            ],
        )
    ]
    project.programs = [
        ProgramUnit(
            uid="m1",
            name="M",
            implementation_language="ladder",
            ladder_networks=[
                LadderNetwork(
                    title="N",
                    rows=1,
                    columns=8,
                    format_version=2,
                    rungs=rungs,
                    cells=[],
                )
            ],
        )
    ]
    save_project_json(project, path)
    loaded = load_project_json(path)
    el = loaded.programs[0].ladder_networks[0].rungs[0].elements[0]
    assert el.branch_group_id == "G1"
    assert el.spec_id == "omron.parallel_open"
