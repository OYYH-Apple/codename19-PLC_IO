# -*- coding: utf-8 -*-
from pathlib import Path

from openpyxl import Workbook

from omron_io_planner.io_excel import import_flat_table, import_io_sheet


def _all_points(proj):
    return [p for c in proj.channels for p in c.points]


def _write_legacy_blocks(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "IO表"
    ws.append(["PLC-01"])
    ws.append(["IN", None, "IN", None])
    ws.append(["0.00", "A", "1.00", "B"])
    ws.append(["0.01", "C", "1.01", "D"])
    ws.append(["OUT", None, "OUT", None])
    ws.append(["100.00", "O1", "101.00", "O2"])
    wb.save(path)


def _write_omron_header(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["名称", "数据类型", "地址/值", "注释", "机架位置", "使用"])
    ws.append(["P_First_Cycle", "BOOL", "A200.11", "第一次循环标志", "", "工作"])
    ws.append(["P_Max_Cycle_Time", "UDINT", "A262", "最长周期时间", "", "工作"])
    wb.save(path)


def test_import_legacy_io_sheet(tmp_path: Path) -> None:
    p = tmp_path / "t.xlsx"
    _write_legacy_blocks(p)
    proj = import_io_sheet(p)
    assert len(_all_points(proj)) == 6
    addrs = {x.address for x in _all_points(proj)}
    assert "0.00" in addrs and "100.00" in addrs


def test_import_flat_with_omron_header(tmp_path: Path) -> None:
    p = tmp_path / "gen.xlsx"
    _write_omron_header(p)
    proj = import_flat_table(p, sheet_index=0)
    pts = _all_points(proj)
    assert len(pts) == 2
    assert pts[0].name == "P_First_Cycle" and pts[0].data_type == "BOOL"
    assert pts[1].data_type == "UDINT" and pts[1].address == "A262"
