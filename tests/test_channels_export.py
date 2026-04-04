# -*- coding: utf-8 -*-
from omron_io_planner.export import rows_io_preview_stitched, stitched_points
from omron_io_planner.models import IoChannel, IoPoint, IoProject


def test_stitched_order_follows_name_list() -> None:
    p1 = IoPoint(name="a", data_type="BOOL", address="0.00", comment="a")
    p2 = IoPoint(name="b", data_type="BOOL", address="1.00", comment="b")
    proj = IoProject(
        channels=[
            IoChannel("A", [p1]),
            IoChannel("B", [p2]),
        ]
    )
    rows = rows_io_preview_stitched(proj, ["B", "A"])
    assert rows[1][0] == "B" and rows[1][4] == "b"
    assert rows[2][0] == "A" and rows[2][4] == "a"
    pts = stitched_points(proj, ["B", "A"])
    assert [x.address for x in pts] == ["1.00", "0.00"]
