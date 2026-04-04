# -*- coding: utf-8 -*-
"""
项目管理器：最近文件、自动保存、持久化配置。

数据保存到用户 AppData 目录（Windows）或 ~/.config 目录（其他平台）。
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import time
from pathlib import Path
from typing import Optional

from .models import IoProject
from .persistence import load_project_json, project_from_dict, save_project_json

# ──────────────────────────────────────────────────────────────────────────────
# 路径解析
# ──────────────────────────────────────────────────────────────────────────────

def _app_data_dir() -> Path:
    """返回应用专属配置/数据目录，自动创建。"""
    name = "OmronIoPlanner"
    sys = platform.system()
    if sys == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    return d


_APP_DIR     = _app_data_dir()
_PREFS_FILE  = _APP_DIR / "prefs.json"
_AUTOSAVE_FILE = _APP_DIR / "autosave.json"
_MAX_RECENT  = 10


def _project_to_dict(project: IoProject) -> dict:
    return {
        "name": project.name,
        "plc_prefix": project.plc_prefix,
        "channels": [
            {
                "name": channel.name,
                "zone_id": channel.zone_id,
                "points": [
                    {
                        "name": point.name,
                        "data_type": point.data_type,
                        "address": point.address,
                        "comment": point.comment,
                        "rack": point.rack,
                        "usage": point.usage,
                    }
                    for point in channel.points
                ],
            }
            for channel in project.channels
        ],
    }


# ──────────────────────────────────────────────────────────────────────────────
# 偏好配置（最近文件等）
# ──────────────────────────────────────────────────────────────────────────────

class Prefs:
    """读写持久化偏好设置。"""

    def __init__(self) -> None:
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            if _PREFS_FILE.exists():
                self._data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            _PREFS_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── 最近文件 ──────────────────────────────────────────────────────────

    def recent_files(self) -> list[str]:
        return list(self._data.get("recent_files", []))

    def add_recent(self, path: str | Path) -> None:
        p = str(Path(path).resolve())
        lst: list[str] = self._data.get("recent_files", [])
        # 去重并移到头部
        if p in lst:
            lst.remove(p)
        lst.insert(0, p)
        self._data["recent_files"] = lst[:self.recent_limit()]
        self._save()

    def remove_recent(self, path: str | Path) -> None:
        p = str(Path(path).resolve())
        lst: list[str] = self._data.get("recent_files", [])
        if p in lst:
            lst.remove(p)
        self._data["recent_files"] = lst
        self._save()

    def clear_recent(self) -> None:
        self._data["recent_files"] = []
        self._save()

    def recent_limit(self) -> int:
        return max(1, int(self._data.get("recent_limit", _MAX_RECENT)))

    def set_recent_limit(self, value: int) -> None:
        self._data["recent_limit"] = max(1, int(value))
        self._data["recent_files"] = self.recent_files()[:self.recent_limit()]
        self._save()

    def show_recent_full_path(self) -> bool:
        return bool(self._data.get("show_recent_full_path", False))

    def set_show_recent_full_path(self, value: bool) -> None:
        self._data["show_recent_full_path"] = bool(value)
        self._save()

    # ── 上次打开的目录 ────────────────────────────────────────────────────

    def last_dir(self) -> str:
        return self._data.get("last_dir", str(Path.home()))

    def set_last_dir(self, path: str | Path) -> None:
        self._data["last_dir"] = str(Path(path).parent)
        self._save()

    # ── 自动保存开关 ──────────────────────────────────────────────────────

    def autosave_enabled(self) -> bool:
        return bool(self._data.get("autosave_enabled", True))

    def set_autosave_enabled(self, v: bool) -> None:
        self._data["autosave_enabled"] = v
        self._save()

    # ── 自动保存间隔（秒） ────────────────────────────────────────────────

    def autosave_interval(self) -> int:
        return int(self._data.get("autosave_interval", 120))  # 默认 2 分钟

    def set_autosave_interval(self, seconds: int) -> None:
        self._data["autosave_interval"] = max(30, seconds)
        self._save()


# ──────────────────────────────────────────────────────────────────────────────
# 自动保存
# ──────────────────────────────────────────────────────────────────────────────

def autosave(project: IoProject, source_path: str | Path | None = None) -> None:
    """将项目写到自动保存槽（覆盖）。"""
    try:
        resolved_source = Path(source_path).resolve() if source_path else None
        payload = {
            "saved_path": str(resolved_source) if resolved_source else "",
            "saved_mtime": (
                resolved_source.stat().st_mtime
                if resolved_source and resolved_source.exists()
                else 0.0
            ),
            "timestamp": time.time(),
            "project": _project_to_dict(project),
        }
        _AUTOSAVE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_autosave() -> IoProject | None:
    """加载自动保存槽，若不存在或解析失败则返回 None。"""
    if not _AUTOSAVE_FILE.exists():
        return None
    try:
        payload = json.loads(_AUTOSAVE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("project"), dict):
            return project_from_dict(payload["project"])
        return project_from_dict(payload)
    except Exception:
        return None


def autosave_exists() -> bool:
    return _AUTOSAVE_FILE.exists()


def autosave_needs_recovery() -> bool:
    if not _AUTOSAVE_FILE.exists():
        return False

    try:
        payload = json.loads(_AUTOSAVE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return True

    if not isinstance(payload, dict):
        return True

    saved_path = str(payload.get("saved_path", "")).strip()
    saved_mtime = float(payload.get("saved_mtime", 0.0) or 0.0)
    if not saved_path:
        return True

    target = Path(saved_path)
    if not target.exists():
        return True

    try:
        current_saved_mtime = target.stat().st_mtime
        current_autosave_mtime = _AUTOSAVE_FILE.stat().st_mtime
    except Exception:
        return True

    baseline = max(saved_mtime, current_autosave_mtime)
    return current_saved_mtime + 1e-6 < baseline


def autosave_mtime() -> float:
    """返回自动保存文件的修改时间（epoch）。若不存在返回 0。"""
    try:
        return _AUTOSAVE_FILE.stat().st_mtime
    except Exception:
        return 0.0


def clear_autosave() -> bool:
    try:
        if _AUTOSAVE_FILE.exists():
            _AUTOSAVE_FILE.unlink()
        return True
    except Exception:
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# 便捷函数
# ──────────────────────────────────────────────────────────────────────────────

_prefs: Prefs | None = None


def get_prefs() -> Prefs:
    global _prefs
    if _prefs is None:
        _prefs = Prefs()
    return _prefs
