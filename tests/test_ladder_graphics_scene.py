# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid

from PySide6.QtWidgets import QGraphicsView

from omron_io_planner.program_models import LadderInstructionInstance, LadderNetwork, LadderRung
from omron_io_planner.ui.ladder_graphics_scene import LadderGraphicsScene


def test_ladder_graphics_rebuild_includes_unknown_spec(qtbot) -> None:
    scene = LadderGraphicsScene()
    view = QGraphicsView(scene)
    qtbot.addWidget(view)

    rungs = [
        LadderRung(
            index=0,
            elements=[
                LadderInstructionInstance(
                    instance_id=str(uuid.uuid4()),
                    spec_id="omron.ld",
                    operands=["A"],
                    slot_index=0,
                ),
                LadderInstructionInstance(
                    instance_id=str(uuid.uuid4()),
                    spec_id="omron.unknown_future",
                    operands=["X"],
                    slot_index=1,
                ),
            ],
        )
    ]
    net = LadderNetwork(
        title="N",
        rows=1,
        columns=8,
        format_version=2,
        rungs=rungs,
        cells=[],
    )
    scene.rebuild(net)
    assert scene.instruction_block_count() == 2


def test_take_pending_slot_consumes_once() -> None:
    scene = LadderGraphicsScene()
    scene._set_pending_slot(1, 3)  # noqa: SLF001
    assert scene.take_pending_slot() == (1, 3)
    assert scene.take_pending_slot() is None


def test_discard_pending_clears() -> None:
    scene = LadderGraphicsScene()
    scene._set_pending_slot(0, 2)  # noqa: SLF001
    scene.discard_pending_slot()
    assert scene.take_pending_slot() is None
