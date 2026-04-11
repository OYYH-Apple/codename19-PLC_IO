# -*- coding: utf-8 -*-
from __future__ import annotations

from omron_io_planner.models import IoChannel, IoPoint, IoProject
from omron_io_planner.persistence import load_project_json, save_project_json
from omron_io_planner.program_models import (
    FunctionBlock,
    LadderCell,
    LadderElement,
    LadderNetwork,
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
                VariableDecl(name="Step", data_type="INT", category="VAR", comment="步骤"),
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
    assert loaded.programs[0].ladder_networks[0].cells[0].element.kind == "contact_no"
    assert loaded.programs[0].ladder_networks[0].cells[1].element.operand == "MotorRun"
    assert loaded.function_blocks[0].variables[1].category == "OUT"
    assert "Step := 1" in loaded.function_blocks[0].st_document.source
    assert loaded.workspace_state["program_workspace"]["selected_item"] == "fb:fb-1:body"
