# -*- coding: utf-8 -*-
"""主窗口共享常量（列索引、预览表头、应用标题等）。"""
from __future__ import annotations

from ..omron_symbol_types import combo_items
from .io_table_widget import IoTableWidget

# 列索引常量（与 IoTableWidget 保持一致）
COL_NAME = IoTableWidget.COL_NAME
COL_DTYPE = IoTableWidget.COL_DTYPE
COL_ADDR = IoTableWidget.COL_ADDR
COL_COMMENT = IoTableWidget.COL_COMMENT
COL_RACK = IoTableWidget.COL_RACK
COL_USAGE = IoTableWidget.COL_USAGE

PREVIEW_LABEL = "全通道预览"
LEGACY_PREVIEW_LABEL = "📊 全通道预览"
PREVIEW_TABLE_HEADERS = ["分区", "名称", "数据类型", "地址/值", "注释", "机架位置", "使用"]
PREVIEW_COLUMN_WIDTH_LIMITS = {
    0: (84, 140),
    1: (120, 320),
    2: (96, 140),
    3: (96, 150),
    4: (120, 420),
    5: (96, 220),
    6: (96, 260),
}

APP_TITLE = "欧姆龙 IO 分配助手"
VALID_DATA_TYPES = set(combo_items())
FALLBACK_EDITOR_DEFAULTS = {
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
