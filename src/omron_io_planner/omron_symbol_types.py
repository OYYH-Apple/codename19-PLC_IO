# -*- coding: utf-8 -*-
"""
欧姆龙 CX-Programmer 符号/IO 表中常见的「数据类型」字符串。

完整、权威的说明请以欧姆龙官方《CX-Programmer Operation Manual》(手册号 W446) 为准，例如：
https://files.omron.eu/downloads/latest/manual/en/w446_cx-programmer_operation_manual_en.pdf

下列名称与公开资料中对上述手册的归纳一致（BOOL、WORD、UDINT、CHANNEL 等），
便于本应用下拉框与导出 TSV 对齐软件界面，不等同于替代官方文档。
参考归纳：https://plc.home.blog/2018/08/22/omron-plc-data-type/
"""

from __future__ import annotations

from typing import List, Tuple

# 下拉框展示顺序：常用位/字类型靠前，其余按手册常见命名列出
OMRON_SYMBOL_DATA_TYPES: Tuple[str, ...] = (
    "BOOL",
    "WORD",
    "UINT",
    "UINT_BCD",
    "UDINT",
    "UDINT_BCD",
    "INT",
    "DINT",
    "LINT",
    "ULINT",
    "ULINT_BCD",
    "DWORD",
    "LWORD",
    "REAL",
    "LREAL",
    "CHANNEL",
    "NUMBER",
)

_DEFAULT = "BOOL"


def normalize_data_type(raw: str) -> str:
    """将导入的字符串规范为已知类型名；未知则原样保留（便于与软件中自定义写法一致）。"""
    t = (raw or "").strip().upper().replace(" ", "_")
    if not t:
        return _DEFAULT
    for known in OMRON_SYMBOL_DATA_TYPES:
        if t == known.upper():
            return known
    return raw.strip() or _DEFAULT


def combo_items() -> List[str]:
    return list(OMRON_SYMBOL_DATA_TYPES)
