# -*- coding: utf-8 -*-
from omron_io_planner.st_loose_format import format_st_document, toggle_st_line_comment


def test_format_st_trims_and_expands_tabs() -> None:
    raw = "  a\tb  \r\n\tc  \n\n\n"
    out = format_st_document(raw, tab_columns=4)
    assert "  a" in out
    assert out.endswith("\n")
    assert "\r" not in out


def test_format_st_collapses_many_blank_lines() -> None:
    raw = "x\n\n\n\n\ny\n"
    out = format_st_document(raw)
    # 连续空行最多保留 2 行，不应再出现 4 个连续换行（即 3 个以上空行）
    assert "\n\n\n\n" not in out


def test_toggle_st_line_comment_wraps_and_unwraps() -> None:
    assert toggle_st_line_comment("    x := 1;") == "    (* x := 1; *)"
    assert toggle_st_line_comment("    (* x := 1; *)") == "    x := 1;"
    assert toggle_st_line_comment("") == "(*  *)"
    assert toggle_st_line_comment("(*  *)") == ""
