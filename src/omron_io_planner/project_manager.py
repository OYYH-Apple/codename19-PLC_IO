# -*- coding: utf-8 -*-
"""
项目管理器：最近文件、自动保存、持久化配置。

数据保存到用户 AppData 目录（Windows）或 ~/.config 目录（其他平台）。
"""
from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Optional

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

_DEFAULT_STARTUP_PREFS = {
    "remember_window_state": False,
    "saved_window_rect": [],
    "auto_open_recent": False,
    "show_recent_sidebar": True,
}

_DEFAULT_EDITOR_DEFAULTS = {
    "continuous_entry": True,
    "enter_navigation": "down",
    "tab_navigation": "right",
    "auto_increment_address": True,
    "inherit_data_type": True,
    "inherit_rack": True,
    "inherit_usage": True,
    "auto_increment_name": True,
    "auto_increment_comment": True,
    "suggestions_enabled": True,
    "suggestion_limit": 8,
    "default_immersive": False,
    "row_height": 34,
    "default_column_layout": {},
    "name_phrases": [],
    "comment_phrases": [],
    "generation_defaults": {
        "start_address": "",
        "row_count": 8,
        "data_type": "BOOL",
        "name_template": "",
        "comment_template": "",
        "rack": "",
        "usage": "",
    },
}

_DEFAULT_RECENT_WORKSPACE_PREFS = {
    "auto_prune_missing": True,
    "allow_pinned": True,
}


def _project_to_dict(project: IoProject) -> dict:
    return {
        "name": project.name,
        "plc_prefix": project.plc_prefix,
        "workspace_state": project.workspace_state,
        "project_preferences": project.project_preferences,
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

    def _merged_group(self, name: str, defaults: dict[str, Any]) -> dict[str, Any]:
        current = self._data.get(name)
        merged = json.loads(json.dumps(defaults, ensure_ascii=False))
        if isinstance(current, dict):
            for key, value in current.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
        return merged

    def _set_group(self, name: str, values: dict[str, Any], defaults: dict[str, Any]) -> None:
        merged = self._merged_group(name, defaults)
        for key, value in values.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        self._data[name] = merged
        self._save()

    def startup_preferences(self) -> dict[str, Any]:
        return self._merged_group("startup", _DEFAULT_STARTUP_PREFS)

    def set_startup_preferences(self, values: dict[str, Any]) -> None:
        self._set_group("startup", values, _DEFAULT_STARTUP_PREFS)

    def editor_defaults(self) -> dict[str, Any]:
        return self._merged_group("editor_defaults", _DEFAULT_EDITOR_DEFAULTS)

    def set_editor_defaults(self, values: dict[str, Any]) -> None:
        self._set_group("editor_defaults", values, _DEFAULT_EDITOR_DEFAULTS)

    def recent_workspace_preferences(self) -> dict[str, Any]:
        return self._merged_group("recent_workspace", _DEFAULT_RECENT_WORKSPACE_PREFS)

    def set_recent_workspace_preferences(self, values: dict[str, Any]) -> None:
        self._set_group("recent_workspace", values, _DEFAULT_RECENT_WORKSPACE_PREFS)

    def _normalize_recent_entry(self, raw: Any) -> dict[str, Any] | None:
        path_value = ""
        pinned = False
        last_opened = 0.0
        last_saved = 0.0
        saved_mtime = 0.0
        if isinstance(raw, str):
            path_value = raw
        elif isinstance(raw, dict):
            path_value = str(raw.get("path", "")).strip()
            pinned = bool(raw.get("pinned", False))
            last_opened = float(raw.get("last_opened", 0.0) or 0.0)
            last_saved = float(raw.get("last_saved", 0.0) or 0.0)
            saved_mtime = float(raw.get("saved_mtime", 0.0) or 0.0)
        if not path_value:
            return None
        try:
            path_value = str(Path(path_value).resolve())
        except Exception:
            path_value = str(Path(path_value))
        return {
            "path": path_value,
            "pinned": pinned,
            "last_opened": last_opened,
            "last_saved": last_saved,
            "saved_mtime": saved_mtime,
        }

    def _sort_recent_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allow_pinned = bool(self.recent_workspace_preferences().get("allow_pinned", True))
        return sorted(
            entries,
            key=lambda entry: (
                0 if allow_pinned and bool(entry.get("pinned")) else 1,
                -float(entry.get("last_opened", 0.0) or 0.0),
                str(entry.get("path", "")).casefold(),
            ),
        )

    def _recent_entries(self) -> list[dict[str, Any]]:
        raw_entries = self._data.get("recent_projects")
        entries: list[dict[str, Any]] = []
        if isinstance(raw_entries, list):
            for raw in raw_entries:
                normalized = self._normalize_recent_entry(raw)
                if normalized is not None:
                    entries.append(normalized)
        else:
            legacy = self._data.get("recent_files", [])
            if isinstance(legacy, list):
                for raw in legacy:
                    normalized = self._normalize_recent_entry(raw)
                    if normalized is not None:
                        entries.append(normalized)
        entries = self._sort_recent_entries(entries)
        self._data["recent_projects"] = entries[: self.recent_limit()]
        return list(self._data["recent_projects"])

    # ── 最近文件 ──────────────────────────────────────────────────────────

    def recent_projects(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._recent_entries()]

    def recent_files(self) -> list[str]:
        return [str(entry["path"]) for entry in self._recent_entries()]

    def add_recent(self, path: str | Path) -> None:
        p = str(Path(path).resolve())
        entries = self._recent_entries()
        existing = next((entry for entry in entries if entry["path"] == p), None)
        if existing is None:
            existing = self._normalize_recent_entry(p)
            assert existing is not None
            entries.append(existing)
        existing["last_opened"] = time.time()
        self._data["recent_projects"] = self._sort_recent_entries(entries)[: self.recent_limit()]
        self._save()

    def mark_recent_saved(self, path: str | Path) -> None:
        p = str(Path(path).resolve())
        entries = self._recent_entries()
        existing = next((entry for entry in entries if entry["path"] == p), None)
        if existing is None:
            existing = self._normalize_recent_entry(p)
            assert existing is not None
            entries.append(existing)
        existing["last_saved"] = time.time()
        try:
            existing["saved_mtime"] = Path(p).stat().st_mtime
        except Exception:
            existing["saved_mtime"] = 0.0
        self._data["recent_projects"] = self._sort_recent_entries(entries)[: self.recent_limit()]
        self._save()

    def remove_recent(self, path: str | Path) -> None:
        p = str(Path(path).resolve())
        entries = [entry for entry in self._recent_entries() if entry["path"] != p]
        self._data["recent_projects"] = self._sort_recent_entries(entries)
        self._save()

    def clear_recent(self) -> None:
        self._data["recent_projects"] = []
        self._save()

    def set_recent_pinned(self, path: str | Path, pinned: bool) -> None:
        p = str(Path(path).resolve())
        entries = self._recent_entries()
        existing = next((entry for entry in entries if entry["path"] == p), None)
        if existing is None:
            existing = self._normalize_recent_entry(p)
            assert existing is not None
            entries.append(existing)
        existing["pinned"] = bool(pinned)
        self._data["recent_projects"] = self._sort_recent_entries(entries)[: self.recent_limit()]
        self._save()

    def recent_limit(self) -> int:
        return max(1, int(self._data.get("recent_limit", _MAX_RECENT)))

    def set_recent_limit(self, value: int) -> None:
        self._data["recent_limit"] = max(1, int(value))
        self._data["recent_projects"] = self._recent_entries()[: self.recent_limit()]
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
