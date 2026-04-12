# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid

from omron_io_planner.ladder_static_validate import (
    validate_ladder_network,
    validate_rung_series_topology,
)
from omron_io_planner.program_models import LadderInstructionInstance, LadderNetwork, LadderRung


def _i(spec_id: str, slot: int, *, op0: str = "", bg: str = "") -> LadderInstructionInstance:
    ops = [op0] if op0 else []
    return LadderInstructionInstance(
        instance_id=str(uuid.uuid4()),
        spec_id=spec_id,
        operands=ops,
        slot_index=slot,
        branch_group_id=bg or op0,
    )


def _net_v2(title: str, rungs: list[LadderRung]) -> LadderNetwork:
    return LadderNetwork(
        title=title,
        rows=len(rungs),
        columns=8,
        cells=[],
        format_version=2,
        rungs=rungs,
    )


def test_series_two_ld_errors() -> None:
    els = [_i("omron.ld", 0, op0="A"), _i("omron.ld", 1, op0="B")]
    err = validate_rung_series_topology(els)
    assert any("最右" in e for e in err)


def test_unknown_spec_error() -> None:
    net = _net_v2(
        "N1",
        [LadderRung(index=0, elements=[_i("omron.unknown_xyz", 0, op0="X")])],
    )
    issues = validate_ladder_network(net)
    assert any(i.spec_id == "omron.unknown_xyz" for i in issues)


def test_required_operand_empty_error() -> None:
    net = _net_v2(
        "N1",
        [LadderRung(index=0, elements=[_i("omron.ld", 0, op0="A"), _i("omron.out", 1, op0="")])],
    )
    issues = validate_ladder_network(net)
    assert any("必填" in i.message_zh for i in issues)


def test_parallel_unclosed_network_error() -> None:
    net = _net_v2(
        "N1",
        [
            LadderRung(
                index=0,
                elements=[_i("omron.parallel_open", 0, op0="A"), _i("omron.ld", 1, op0="X")],
            )
        ],
    )
    issues = validate_ladder_network(net)
    assert any("未闭合" in i.message_zh or "闭合" in i.message_zh for i in issues)


def test_clean_ld_out_no_errors() -> None:
    net = _net_v2(
        "N1",
        [LadderRung(index=0, elements=[_i("omron.ld", 0, op0="A"), _i("omron.out", 1, op0="B")])],
    )
    assert validate_ladder_network(net) == []


def test_unknown_symbol_warning_optional() -> None:
    net = _net_v2(
        "N1",
        [LadderRung(index=0, elements=[_i("omron.ld", 0, op0="A"), _i("omron.out", 1, op0="GhostSym")])],
    )
    assert validate_ladder_network(net, known_symbols={"A"}, check_unknown_symbols=False) == []
    w = validate_ladder_network(net, known_symbols={"A"}, check_unknown_symbols=True)
    assert any(i.severity == "warning" and "GhostSym" in i.message_zh for i in w)
