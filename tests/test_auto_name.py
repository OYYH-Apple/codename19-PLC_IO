# -*- coding: utf-8 -*-
from __future__ import annotations

from omron_io_planner.auto_name import build_auto_name, normalize_comment_fragment, normalize_zone_prefix


def test_build_auto_name_uses_zone_address_and_comment() -> None:
    assert build_auto_name("CIO", "0.01", "阻挡气缸伸出") == "CIO_0.01_阻挡气缸伸出"


def test_build_auto_name_uses_placeholder_when_comment_empty() -> None:
    assert build_auto_name("WR", "10.00", "") == "W_10.00_待注释"


def test_build_auto_name_uses_placeholder_when_address_invalid() -> None:
    assert build_auto_name("DM", "invalid-address", "阻挡气缸伸出") == "D_待分配_阻挡气缸伸出"


def test_build_auto_name_falls_back_to_io_for_custom_channels() -> None:
    assert build_auto_name("", "", "顶升气缸伸出") == "IO_待分配_顶升气缸伸出"


def test_normalize_comment_fragment_collapses_separators() -> None:
    assert normalize_comment_fragment(" 阻挡气缸 / 伸出-到位. ") == "阻挡气缸_伸出_到位"


def test_normalize_zone_prefix_uses_standard_short_name() -> None:
    assert normalize_zone_prefix("WR") == "W"
    assert normalize_zone_prefix("DM") == "D"
    assert normalize_zone_prefix("custom") == "IO"
