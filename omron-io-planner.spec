# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import struct


SPEC_ROOT = Path(SPECPATH).resolve()
APP_LAUNCHER = SPEC_ROOT / 'app_launcher.py'
APP_ICON_PNG = SPEC_ROOT / 'logo.png'
APP_ICON_ICO = SPEC_ROOT / 'build' / 'logo.ico'
UI_ICON_DIR = SPEC_ROOT / 'src' / 'omron_io_planner' / 'ui' / 'assets' / 'icons'


def _png_to_ico(png_path: Path, ico_path: Path) -> str:
    png_bytes = png_path.read_bytes()
    if png_bytes[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'Invalid PNG icon: {png_path}')
    width = int.from_bytes(png_bytes[16:20], 'big')
    height = int.from_bytes(png_bytes[20:24], 'big')
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    icon_dir = struct.pack('<HHH', 0, 1, 1)
    icon_entry = struct.pack(
        '<BBBBHHII',
        0 if width >= 256 else width,
        0 if height >= 256 else height,
        0,
        0,
        1,
        32,
        len(png_bytes),
        22,
    )
    ico_path.write_bytes(icon_dir + icon_entry + png_bytes)
    return str(ico_path)


a = Analysis(
    [str(APP_LAUNCHER)],
    pathex=[str(SPEC_ROOT / 'src')],
    binaries=[],
    datas=[
        (str(UI_ICON_DIR), 'omron_io_planner/ui/assets/icons'),
        (str(APP_ICON_PNG), '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='omron-io-planner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=_png_to_ico(APP_ICON_PNG, APP_ICON_ICO),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='omron-io-planner',
)
