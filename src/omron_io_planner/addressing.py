# -*- coding: utf-8 -*-
"""CIO 位地址解析与格式化（欧姆龙 CP 常用 字.位 记法）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

_RE_BIT = re.compile(r"^\s*(\d+)\s*\.\s*(\d+)\s*$")


def parse_cio_bit(text: str) -> Optional[Tuple[int, int]]:
    """解析 '0.00' / '100.05' 为 (字, 位)。"""
    if text is None:
        return None
    m = _RE_BIT.match(str(text).strip())
    if not m:
        return None
    w, b = int(m.group(1)), int(m.group(2))
    if b < 0 or b > 15:
        return None
    return w, b


def format_cio_bit(word: int, bit: int) -> str:
    return f"{word}.{bit:02d}"


def next_bit(addr: str, step: int = 1) -> Optional[str]:
    """在同一字内递增位；跨字时返回 None（由调用方处理）。"""
    t = parse_cio_bit(addr)
    if t is None:
        return None
    w, b = t
    nb = b + step
    if 0 <= nb <= 15:
        return format_cio_bit(w, nb)
    return None


def increment_word(addr: str, delta_word: int) -> Optional[str]:
    t = parse_cio_bit(addr)
    if t is None:
        return None
    w, b = t
    return format_cio_bit(w + delta_word, b)
