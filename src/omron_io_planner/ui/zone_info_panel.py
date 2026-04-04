# -*- coding: utf-8 -*-
"""
分区信息侧边栏组件。

显示当前欧姆龙数据分区的：
  - 区域名称 + 徽章
  - 地址前缀 / 示例
  - 主要用途
  - 掉电保持特性
  - 支持访问方式
  - 典型容量
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..omron_zones import OmronZone, get_zone


def _row_html(label: str, value: str, label_color: str = "#6A7090") -> str:
    return (
        f'<p style="margin:0 0 6px 0;">'
        f'<span style="color:{label_color};font-size:8pt;font-weight:bold;">{label}</span><br>'
        f'<span style="color:#1E2235;font-size:9pt;">{value}</span>'
        f"</p>"
    )


class ZoneInfoPanel(QWidget):
    """显示单个欧姆龙分区详情的侧边面板。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # 顶部颜色条 + 区域名
        self._header = QLabel()
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header.setMinimumHeight(52)
        self._header.setStyleSheet(
            "border-radius: 6px 6px 0 0; padding: 6px; "
            "font-size: 11pt; font-weight: bold; color: white;"
        )
        self._layout.addWidget(self._header)

        # 内容区
        self._body_frame = QFrame()
        self._body_frame.setStyleSheet(
            "QFrame { background: #F0F3FA; border: 1px solid #C8CDD8; "
            "border-top: none; border-radius: 0 0 6px 6px; padding: 0; }"
        )
        body_v = QVBoxLayout(self._body_frame)
        body_v.setContentsMargins(10, 10, 10, 10)
        body_v.setSpacing(2)

        self._content_label = QLabel()
        self._content_label.setWordWrap(True)
        self._content_label.setTextFormat(Qt.TextFormat.RichText)
        self._content_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._content_label.setStyleSheet("background: transparent; border: none;")
        body_v.addWidget(self._content_label)
        body_v.addStretch()

        self._layout.addWidget(self._body_frame, stretch=1)

        # 默认空状态
        self._set_empty()

    def _set_empty(self) -> None:
        self._header.setText("分区信息")
        self._header.setStyleSheet(
            "background-color: #8090B0; border-radius: 6px 6px 0 0; "
            "padding: 6px; font-size: 11pt; font-weight: bold; color: white;"
        )
        self._content_label.setText(
            '<p style="color:#8090B0;font-size:9pt;">（自定义通道，无标准分区信息）</p>'
        )

    def set_zone(self, zone: OmronZone | None) -> None:
        """切换显示的分区信息。"""
        if zone is None:
            self._set_empty()
            return

        # 头部
        badge_html = (
            f' <span style="font-size:8pt;background:rgba(255,255,255,0.25);'
            f'border-radius:4px;padding:1px 5px;">{zone.badge}</span>'
            if zone.badge else ""
        )
        self._header.setText(f"{zone.display_name}{badge_html}")
        self._header.setStyleSheet(
            f"background-color: {zone.color}; border-radius: 6px 6px 0 0; "
            f"padding: 8px 6px; font-size: 10pt; font-weight: bold; color: white;"
        )
        self._header.setTextFormat(Qt.TextFormat.RichText)

        # 内容
        html = (
            _row_html("📌 地址示例", zone.prefix_example, "#5A6A9A")
            + _row_html("🔧 主要用途", zone.main_usage, "#5A6A9A")
            + _row_html("🔋 掉电保持", zone.retention, "#5A6A9A")
            + _row_html("🔑 访问方式", zone.access_modes, "#5A6A9A")
            + _row_html("📦 典型容量", zone.capacity, "#5A6A9A")
        )
        self._content_label.setText(html)

    def set_zone_by_id(self, zone_id: str) -> None:
        """根据 zone_id 字符串设置分区（空串 → 空状态）。"""
        if not zone_id:
            self._set_empty()
            return
        self.set_zone(get_zone(zone_id))
