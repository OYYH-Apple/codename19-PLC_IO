# -*- coding: utf-8 -*-
from omron_io_planner.omron_symbol_types import normalize_data_type


def test_normalize_known() -> None:
    assert normalize_data_type("bool") == "BOOL"
    assert normalize_data_type("Udint") == "UDINT"


def test_normalize_unknown_preserved() -> None:
    assert normalize_data_type("CUSTOM_X") == "CUSTOM_X"
