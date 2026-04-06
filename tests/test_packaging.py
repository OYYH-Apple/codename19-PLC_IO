# -*- coding: utf-8 -*-
from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_pyinstaller_launcher_invokes_package_main(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("omron_io_planner.app.main", lambda: calls.append("main"))

    runpy.run_path(str(ROOT / "app_launcher.py"), run_name="__main__")

    assert calls == ["main"]


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


def test_resolve_app_icon_path_uses_repo_logo_when_running_from_source() -> None:
    pytest.importorskip("PySide6")
    from omron_io_planner import app as app_module

    assert app_module._resolve_app_icon_path() == ROOT / "logo.png"


def test_resolve_app_icon_path_prefers_frozen_bundle_logo(monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from omron_io_planner import app as app_module

    bundled_logo = tmp_path / "logo.png"
    bundled_logo.write_bytes(b"test")
    monkeypatch.setattr(app_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_module.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert app_module._resolve_app_icon_path() == bundled_logo


def test_pyinstaller_spec_embeds_logo_png_and_icon() -> None:
    spec_text = (ROOT / "omron-io-planner.spec").read_text(encoding="utf-8")

    assert "logo.png" in spec_text
    assert "icon=" in spec_text
