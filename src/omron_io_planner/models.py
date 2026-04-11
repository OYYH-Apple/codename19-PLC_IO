# -*- coding: utf-8 -*-
"""IO 点：对齐欧姆龙符号/IO 表常见列（名称、数据类型、地址/值、注释等）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from .omron_symbol_types import normalize_data_type
from .program_models import FunctionBlock, ProgramUnit


@dataclass
class IoPoint:
    """与 CX-Programmer 风格 IO/符号表对应的一行。"""
    name: str = ""
    data_type: str = "BOOL"
    address: str = ""
    comment: str = ""
    rack: str = ""
    usage: str = ""

    def __post_init__(self) -> None:
        self.data_type = normalize_data_type(self.data_type)

    def display_address(self) -> str:
        return self.address.strip()


@dataclass
class IoChannel:
    name: str
    points: List[IoPoint] = field(default_factory=list)
    zone_id: str = ""          # 对应 OmronZone.zone_id，空串表示自定义通道


@dataclass
class IoProject:
    name: str = "新项目"
    plc_prefix: str = "PLC"
    channels: List[IoChannel] = field(default_factory=list)
    workspace_state: dict[str, Any] = field(default_factory=dict)
    project_preferences: dict[str, Any] = field(default_factory=dict)
    programs: List[ProgramUnit] = field(default_factory=list)
    function_blocks: List[FunctionBlock] = field(default_factory=list)
    program_settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.channels:
            self._init_default_zones()

    def _init_default_zones(self) -> None:
        """按欧姆龙标准分区初始化默认通道列表。"""
        from .omron_zones import ALL_ZONES
        self.channels = [
            IoChannel(name=z.display_name, zone_id=z.zone_id)
            for z in ALL_ZONES
        ]

    def sorted_points(self) -> List[IoPoint]:
        out: List[IoPoint] = []
        for ch in self.channels:
            out.extend(sort_points(ch.points))
        return out

    def unique_channel_name(self, base: str = "自定义") -> str:
        existing = {c.name for c in self.channels}
        n = len(self.channels) + 1
        cand = f"{base}{n}"
        while cand in existing:
            n += 1
            cand = f"{base}{n}"
        return cand


def _addr_sort_key(addr: str) -> tuple:
    from .addressing import parse_cio_bit

    t = parse_cio_bit(addr)
    if t is None:
        return (1, addr.upper())
    w, b = t
    return (0, w, b)


def sort_points(points: List[IoPoint]) -> List[IoPoint]:
    return sorted(
        points,
        key=lambda p: (_addr_sort_key(p.address), (p.name or "").upper()),
    )


def project_single_channel(
    name: str, channel_name: str = "导入", points: Optional[List[IoPoint]] = None
) -> IoProject:
    return IoProject(name=name, channels=[IoChannel(name=channel_name, points=list(points or []))])
