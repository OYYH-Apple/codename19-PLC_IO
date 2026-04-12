# -*- coding: utf-8 -*-
from __future__ import annotations

from omron_io_planner.omron_ladder_spec import validate_instruction_placement


def test_placement_single_ld_ok() -> None:
    ok, msg = validate_instruction_placement(existing_slot_specs=[], target_slot=0, new_spec_id="omron.ld")
    assert ok and msg == ""


def test_placement_single_out_ok() -> None:
    ok, msg = validate_instruction_placement(existing_slot_specs=[], target_slot=2, new_spec_id="omron.out")
    assert ok and msg == ""


def test_placement_ld_then_out_ok() -> None:
    ok, _ = validate_instruction_placement(
        existing_slot_specs=[(0, "omron.ld")],
        target_slot=3,
        new_spec_id="omron.out",
    )
    assert ok


def test_placement_out_in_middle_rejected() -> None:
    ok, msg = validate_instruction_placement(
        existing_slot_specs=[(0, "omron.ld"), (4, "omron.ldnot")],
        target_slot=2,
        new_spec_id="omron.out",
    )
    assert not ok
    assert "串联" in msg or "触点" in msg or "右端" in msg


def test_placement_ld_right_of_out_rejected() -> None:
    ok, msg = validate_instruction_placement(
        existing_slot_specs=[(0, "omron.out")],
        target_slot=4,
        new_spec_id="omron.ld",
    )
    assert not ok
    assert "右端" in msg or "输出" in msg


def test_placement_replace_preserves_order() -> None:
    ok, _ = validate_instruction_placement(
        existing_slot_specs=[(0, "omron.ld"), (4, "omron.out")],
        target_slot=0,
        new_spec_id="omron.ldnot",
    )
    assert ok
