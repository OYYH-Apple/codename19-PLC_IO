# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


def test_wheel_includes_svg_icons(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(dist_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    wheel_path = next(dist_dir.glob("*.whl"))
    with ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())

    assert "omron_io_planner/ui/assets/icons/export.svg" in names
    assert "omron_io_planner/ui/assets/icons/export-light.svg" in names
