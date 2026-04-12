# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid

from omron_io_planner.omron_ladder_topology import validate_rung_parallel_topology
from omron_io_planner.program_models import LadderInstructionInstance


def _inst(spec_id: str, slot: int, *, op0: str = "", bg: str = "") -> LadderInstructionInstance:
    ops = [op0] if op0 else []
    return LadderInstructionInstance(
        instance_id=str(uuid.uuid4()),
        spec_id=spec_id,
        operands=ops,
        slot_index=slot,
        branch_group_id=bg or op0,
    )


def test_parallel_nested_lifo_ok() -> None:
    els = [
        _inst("omron.ld", 0, op0="X"),
        _inst("omron.parallel_open", 1, op0="A"),
        _inst("omron.parallel_open", 2, op0="B"),
        _inst("omron.ld", 3, op0="Y"),
        _inst("omron.parallel_close", 4, op0="B"),
        _inst("omron.parallel_close", 5, op0="A"),
        _inst("omron.out", 6, op0="Z"),
    ]
    assert validate_rung_parallel_topology(els) == []


def test_parallel_unclosed_rejected() -> None:
    els = [
        _inst("omron.parallel_open", 0, op0="A"),
        _inst("omron.ld", 1, op0="X"),
    ]
    err = validate_rung_parallel_topology(els)
    assert err and "未闭合" in err[-1]


def test_parallel_close_without_open() -> None:
    els = [_inst("omron.parallel_close", 0, op0="A")]
    err = validate_rung_parallel_topology(els)
    assert any("栈空" in e or "没有对应" in e for e in err)


def test_parallel_wrong_close_order() -> None:
    els = [
        _inst("omron.parallel_open", 0, op0="A"),
        _inst("omron.parallel_open", 1, op0="B"),
        _inst("omron.parallel_close", 2, op0="A"),
    ]
    err = validate_rung_parallel_topology(els)
    assert any("LIFO" in e or "最内层" in e for e in err)


def test_parallel_duplicate_open_same_group() -> None:
    els = [
        _inst("omron.parallel_open", 0, op0="A"),
        _inst("omron.parallel_open", 1, op0="A"),
    ]
    err = validate_rung_parallel_topology(els)
    assert any("重复" in e for e in err)
