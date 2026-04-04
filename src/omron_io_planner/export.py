# -*- coding: utf-8 -*-
"""剪贴板 / TSV / CSV 导出（表头对齐欧姆龙符号/IO 表常见列）。"""
from __future__ import annotations

import csv
import io
from typing import List, Sequence

from .addressing import parse_cio_bit
from .models import IoPoint, IoProject


def symbol_name_for_point(project: IoProject, p: IoPoint, seq: int) -> str:
    if (p.name or "").strip():
        return p.name.strip()
    pre = project.plc_prefix.replace("-", "_").replace(" ", "_")
    return f"{pre}_SYM_{seq:04d}"


def _omron_row(p: IoPoint) -> List[str]:
    return [
        p.name or "",
        p.data_type or "BOOL",
        p.address or "",
        p.comment or "",
        p.rack or "",
        p.usage or "",
    ]


OMRON_IO_HEADERS = ["名称", "数据类型", "地址/值", "注释", "机架位置", "使用"]


def _project_points_in_order(project: IoProject) -> List[IoPoint]:
    out: List[IoPoint] = []
    for channel in project.channels:
        out.extend(channel.points)
    return out


def rows_io_table(project: IoProject) -> List[List[str]]:
    rows: List[List[str]] = [list(OMRON_IO_HEADERS)]
    for p in _project_points_in_order(project):
        rows.append(_omron_row(p))
    return rows


def rows_io_table_channel(project: IoProject, channel_index: int) -> List[List[str]]:
    rows: List[List[str]] = [list(OMRON_IO_HEADERS)]
    if channel_index < 0 or channel_index >= len(project.channels):
        return rows
    for p in project.channels[channel_index].points:
        rows.append(_omron_row(p))
    return rows


def rows_io_preview_stitched(
    project: IoProject, channel_names_ordered: List[str]
) -> List[List[str]]:
    rows: List[List[str]] = [["通道"] + list(OMRON_IO_HEADERS)]
    by_name = {c.name: c for c in project.channels}
    for name in channel_names_ordered:
        ch = by_name.get(name)
        if ch is None:
            continue
        for p in ch.points:
            r = _omron_row(p)
            rows.append([ch.name] + r)
    return rows


def rows_symbol_table_for_points(project: IoProject, points: List[IoPoint]) -> List[List[str]]:
    rows: List[List[str]] = [["名称", "数据类型", "地址", "注释"]]
    for i, p in enumerate(points):
        sym = symbol_name_for_point(project, p, i)
        dtype = (p.data_type or "BOOL").strip() or "BOOL"
        rows.append([sym, dtype, p.address, p.comment])
    return rows


def rows_symbol_table(project: IoProject) -> List[List[str]]:
    return rows_symbol_table_for_points(project, _project_points_in_order(project))


def rows_d_channel_for_points(project: IoProject, points: List[IoPoint], start_d: int = 0) -> List[List[str]]:
    rows: List[List[str]] = [["名称", "数据类型", "地址", "注释", "备注"]]
    for i, p in enumerate(points):
        sym = symbol_name_for_point(project, p, i)
        rows.append([sym, "CHANNEL", f"D{start_d + i}", p.comment, p.comment])
    return rows


def rows_d_channel(project: IoProject, start_d: int = 0) -> List[List[str]]:
    return rows_d_channel_for_points(project, _project_points_in_order(project), start_d)


def rows_cio_word_index_for_points(project: IoProject, points: List[IoPoint]) -> List[List[str]]:
    rows: List[List[str]] = [["名称", "数据类型", "地址(字)", "注释", "备注"]]
    for i, p in enumerate(points):
        sym = symbol_name_for_point(project, p, i)
        t = parse_cio_bit(p.address)
        idx = "" if t is None else str(t[0])
        rows.append([sym, "CHANNEL", idx, p.comment, p.comment])
    return rows


def rows_cio_word_index(project: IoProject) -> List[List[str]]:
    return rows_cio_word_index_for_points(project, _project_points_in_order(project))


def stitched_points(project: IoProject, channel_names_ordered: List[str]) -> List[IoPoint]:
    by_name = {c.name: c for c in project.channels}
    out: List[IoPoint] = []
    for name in channel_names_ordered:
        ch = by_name.get(name)
        if ch is None:
            continue
        out.extend(ch.points)
    return out


def tsv_from_rows(rows: Sequence[Sequence[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n")
    for r in rows:
        w.writerow(list(r))
    return buf.getvalue()


def csv_from_rows(rows: Sequence[Sequence[str]]) -> str:
    buf = io.StringIO()
    cw = csv.writer(buf, lineterminator="\n")
    for r in rows:
        cw.writerow(list(r))
    return buf.getvalue()


def combined_export_text(project: IoProject) -> str:
    parts: List[str] = []
    parts.append("=== 符号表（名称/数据类型/地址/注释）===")
    parts.append(tsv_from_rows(rows_symbol_table(project)))
    parts.append("")
    parts.append("=== CHANNEL + D 区顺序 ===")
    parts.append(tsv_from_rows(rows_d_channel(project)))
    parts.append("")
    parts.append("=== CHANNEL + CIO 字地址 ===")
    parts.append(tsv_from_rows(rows_cio_word_index(project)))
    return "\n".join(parts)
