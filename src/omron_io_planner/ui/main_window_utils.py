# -*- coding: utf-8 -*-
"""主窗口无状态工具函数与小型控件工厂。"""
from __future__ import annotations

import json

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy

from .icons import load_icon
from .io_table_widget import _next_omron_bit
from .main_window_constants import LEGACY_PREVIEW_LABEL, PREVIEW_LABEL


def _deep_merge(base: dict, override: dict) -> dict:
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _next_address_value(address: str) -> str:
    nxt = _next_omron_bit(address)
    return nxt if nxt else address


def _is_preview_tab_label(label: str) -> bool:
    return label in {PREVIEW_LABEL, LEGACY_PREVIEW_LABEL}


def _make_action_btn(
    text: str,
    tooltip: str = "",
    danger: bool = False,
    compact: bool = False,
    icon_name: str = "",
) -> QPushButton:
    btn = QPushButton(text)
    if tooltip:
        btn.setToolTip(tooltip)
    if danger:
        btn.setProperty("danger", "true")
    if icon_name:
        btn.setIcon(load_icon(icon_name))
        btn.setIconSize(QSize(14, 14))
    if compact:
        btn.setProperty("compact", "true")
        btn.setMinimumWidth(0)
        btn.setMinimumHeight(34)
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return btn


def _make_immersive_btn(
    text: str,
    *,
    tooltip: str = "",
    danger: bool = False,
    icon_name: str = "",
) -> QPushButton:
    btn = _make_action_btn(text, tooltip=tooltip, danger=danger, compact=True, icon_name=icon_name)
    btn.setMinimumWidth(max(82, btn.sizeHint().width()))
    btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return btn
