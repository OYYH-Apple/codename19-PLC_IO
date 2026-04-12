# -*- coding: utf-8 -*-
from __future__ import annotations

from omron_io_planner.cx_emitter import cxr_text_from_ladder_networks
from omron_io_planner.program_models import (
    LadderCell,
    LadderElement,
    LadderNetwork,
    LadderInstructionInstance,
    LadderRung,
)


def test_cxr_emitter_matches_program_export_v1_and_v2() -> None:
    v1_text = cxr_text_from_ladder_networks(
        "主程序 1",
        [
            LadderNetwork(
                title="启动保持",
                rows=4,
                columns=6,
                comment="主回路",
                cells=[
                    LadderCell(1, 1, LadderElement(kind="contact_no", operand="StartPB")),
                    LadderCell(1, 4, LadderElement(kind="coil", operand="MotorRun")),
                ],
            )
        ],
    )
    assert "contact_no" in v1_text
    assert "FORMAT_VERSION" not in v1_text

    rungs = [LadderRung(index=i) for i in range(4)]
    rungs[1].elements = [
        LadderInstructionInstance(
            instance_id="a",
            spec_id="omron.ld",
            operands=["StartPB"],
            slot_index=1,
        ),
        LadderInstructionInstance(
            instance_id="b",
            spec_id="omron.out",
            operands=["MotorRun"],
            slot_index=4,
        ),
    ]
    v2_text = cxr_text_from_ladder_networks(
        "主程序 1",
        [
            LadderNetwork(
                title="启动保持",
                rows=4,
                columns=6,
                comment="主回路",
                cells=[],
                format_version=2,
                rungs=rungs,
            )
        ],
    )
    assert "FORMAT_VERSION\t2" in v2_text
    assert "CELL\t1\t1\tomron.ld\tStartPB\t\t" in v2_text
