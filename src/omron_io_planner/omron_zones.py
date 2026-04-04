# -*- coding: utf-8 -*-
"""
欧姆龙 PLC 数据分区（Zone）定义。

每个分区包含：
  - 唯一 id（用于持久化）
  - 显示名称（选项卡标签）
  - 地址前缀示例
  - 主要用途
  - 掉电保持特性
  - 支持访问方式
  - 典型容量说明
  - 颜色标记（用于选项卡着色）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class OmronZone:
    zone_id: str           # 内部唯一键，如 "CIO"、"WR"、"HR" …
    display_name: str      # 选项卡显示名
    prefix_example: str    # 地址前缀/示例，如 "CIO 0.00 / 100.00"
    main_usage: str        # 主要用途（一句话）
    retention: str         # 掉电保持特性
    access_modes: str      # 支持访问方式
    capacity: str          # 典型容量（视 CPU 型号）
    color: str             # 十六进制颜色，用于选项卡
    badge: str = ""        # 简短徽章文字（显示在选项卡名旁）


# ── 全部预定义分区 ─────────────────────────────────────────────────────────

ALL_ZONES: List[OmronZone] = [
    OmronZone(
        zone_id="CIO",
        display_name="CIO 区",
        prefix_example="0.00 / 100.00 / CIO 200.05",
        main_usage="实际 I/O 点（输入/输出继电器），未用部分作内部继电器",
        retention="部分上电清零，部分保留（取决于区段与设置）",
        access_modes="位访问 + 字访问",
        capacity="0 ~ 6143 字（CP/CJ/CS 系列，具体视 CPU 型号）",
        color="#1A6B8A",
        badge="I/O",
    ),
    OmronZone(
        zone_id="WR",
        display_name="WR 区",
        prefix_example="W0.00 / W100",
        main_usage="临时内部处理、工作位、中间计算（草稿区）",
        retention="上电/重启时通常清零（非保持）",
        access_modes="位访问 + 字访问",
        capacity="0 ~ 511 字（W0 ~ W511）",
        color="#2E7D32",
        badge="Work",
    ),
    OmronZone(
        zone_id="HR",
        display_name="HR 区",
        prefix_example="H0.00 / H100",
        main_usage="需要掉电保持的状态、参数、标志",
        retention="掉电保留（电池或闪存备份）",
        access_modes="位访问 + 字访问",
        capacity="0 ~ 511 字（H0 ~ H511）",
        color="#6A1B9A",
        badge="Hold",
    ),
    OmronZone(
        zone_id="DM",
        display_name="DM 区",
        prefix_example="D0 / D100 / D32767",
        main_usage="大量数据存储、参数、计算结果、配方等",
        retention="掉电可保持（取决于 DM 区设置和 CPU 型号）",
        access_modes="主要字访问，部分支持位访问（.xx）",
        capacity="0 ~ 32767 字（常见），部分 CPU 支持更大",
        color="#BF360C",
        badge="Data",
    ),
    OmronZone(
        zone_id="EM",
        display_name="EM 区",
        prefix_example="E0_0 / E1_100 / E0_32767",
        main_usage="扩展数据存储（更大容量的数据、日志、数组）",
        retention="掉电可保持（闪存/外存备份）",
        access_modes="主要字访问，支持位访问",
        capacity="多 Bank（E0、E1…），每 Bank 约 32768 字，视 CPU 扩展量",
        color="#E65100",
        badge="Ext",
    ),
    OmronZone(
        zone_id="AR",
        display_name="AR 区",
        prefix_example="A0.00 / A100 / A447",
        main_usage="系统特殊辅助继电器、错误标志、时钟脉冲、PLC 状态（部分只读）",
        retention="部分上电保留，部分上电清零（具体见系统寄存器手册）",
        access_modes="位访问 + 字访问（部分字段只读）",
        capacity="0 ~ 959 字（A0 ~ A959），部分区域系统专用",
        color="#37474F",
        badge="Aux",
    ),
    OmronZone(
        zone_id="TIM",
        display_name="定时器区",
        prefix_example="T0 / T100 / T4095",
        main_usage="定时器当前值（PV）和完成标志（TIM/TIMH/TIML 等指令专用）",
        retention="上电清零（PV 值和完成位均复位）",
        access_modes="字访问（PV）+ 位访问（完成标志）",
        capacity="T0 ~ T4095（4096 点，具体视 CPU）",
        color="#00695C",
        badge="TIM",
    ),
    OmronZone(
        zone_id="CNT",
        display_name="计数器区",
        prefix_example="C0 / C100 / C4095",
        main_usage="计数器当前值（PV）和完成标志（CNT/CNTR 等指令专用）",
        retention="上电保留 PV（计数器 PV 默认保持，完成标志随 PV 状态）",
        access_modes="字访问（PV）+ 位访问（完成标志）",
        capacity="C0 ~ C4095（4096 点，具体视 CPU）",
        color="#1565C0",
        badge="CNT",
    ),
]

# ── 快速查询字典 ─────────────────────────────────────────────────────────────

_ZONE_BY_ID: dict[str, OmronZone] = {z.zone_id: z for z in ALL_ZONES}


def get_zone(zone_id: str) -> Optional[OmronZone]:
    return _ZONE_BY_ID.get(zone_id)


def default_zone_ids() -> List[str]:
    """新建项目时默认展示的分区列表（全部 8 个）。"""
    return [z.zone_id for z in ALL_ZONES]
