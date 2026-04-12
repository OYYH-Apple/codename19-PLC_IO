# -*- coding: utf-8 -*-
"""ST 文本的轻量「一键整理」：换行统一、行尾空白、Tab 展开、多余空行压缩。"""
from __future__ import annotations

import re


def format_st_document(text: str, *, tab_columns: int = 4) -> str:
    """对整段 ST 做非语义化整理，不改变关键字含义。

    - 统一为 ``\\n``；每行行尾空白去掉；
    - Tab 按 ``tab_columns`` 列宽展开（默认 4，与编辑器 Tab=四空格一致）；
    - 连续空行最多保留 2 行；文末最多保留一个换行。
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = t.split("\n")
    expanded = [ln.expandtabs(tab_columns) for ln in lines]
    stripped = [ln.rstrip() for ln in expanded]

    out: list[str] = []
    blank_run = 0
    for ln in stripped:
        if ln == "":
            blank_run += 1
            if blank_run <= 2:
                out.append("")
        else:
            blank_run = 0
            out.append(ln)
    while out and out[-1] == "":
        out.pop()
    if not out:
        return ""
    return "\n".join(out) + "\n"


_ST_LINE_COMMENT_WRAP = re.compile(r"^(\s*)\(\*\s*(.*?)\s*\*\)\s*$")


def toggle_st_line_comment(line: str) -> str:
    """整行 ``(* … *)`` 切换：已按整行包裹则去掉标记，否则在保留左侧缩进的前提下整行包裹。

    与 ``StructuredTextEditor.insert_comment_snippet`` 的块注释风格一致（``(* `` 与 `` *)``）。
    """
    m = _ST_LINE_COMMENT_WRAP.match(line)
    if m:
        return m.group(1) + m.group(2)
    m2 = re.match(r"^(\s*)(.*)$", line)
    if not m2:
        return line
    ind, body = m2.group(1), m2.group(2)
    return f"{ind}(* {body} *)"
