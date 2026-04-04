# -*- coding: utf-8 -*-
from omron_io_planner.addressing import format_cio_bit, parse_cio_bit


def test_parse_roundtrip():
    assert parse_cio_bit("0.00") == (0, 0)
    assert parse_cio_bit("100.15") == (100, 15)
    assert format_cio_bit(0, 0) == "0.00"
    assert format_cio_bit(100, 5) == "100.05"


def test_parse_none():
    assert parse_cio_bit("") is None
    assert parse_cio_bit("bad") is None
