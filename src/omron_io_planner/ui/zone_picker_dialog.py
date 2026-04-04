# -*- coding: utf-8 -*-
"""
分区选择对话框。

用于让用户选择要添加到项目的欧姆龙标准分区，或添加自定义通道。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..omron_zones import ALL_ZONES, OmronZone
from .dialogs import AppDialog, MessageDialog


class ZonePickerDialog(AppDialog):
    """
    从标准欧姆龙分区列表中选择一个或多个分区添加。
    也可以输入自定义名称。

    result_zone_ids: list[str]  — 选中的 zone_id 列表
    result_zone_id: str | None  — 兼容旧调用，取首个 zone_id，空串表示自定义
    result_custom_name: str      — 自定义名称（zone_id 为空时使用）
    """

    def __init__(self, existing_zone_ids: set[str], parent=None) -> None:
        super().__init__("添加分区 / 通道", object_name="appZonePickerDialog", parent=parent)
        self.setMinimumWidth(400)
        self.setMinimumHeight(440)

        self.result_zone_ids: list[str] = []
        self.result_zone_id: str = ""
        self.result_custom_name: str = ""

        v = self._body_layout
        v.setSpacing(10)

        hint = QLabel("可多选要添加的欧姆龙标准分区（灰色表示已添加），\n或在下方输入自定义通道名称。")
        hint.setStyleSheet("color: #5A6080; font-size: 9pt;")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSpacing(2)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        for zone in ALL_ZONES:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, zone.zone_id)
            item.setText(f"  {zone.display_name}")

            already = zone.zone_id in existing_zone_ids
            if already:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setForeground(Qt.GlobalColor.gray)
                item.setText(f"  {zone.display_name}  （已添加）")
            else:
                # 彩色左边框通过 tooltip 提示颜色
                item.setToolTip(
                    f"{zone.main_usage}\n"
                    f"掉电保持：{zone.retention}\n"
                    f"地址示例：{zone.prefix_example}"
                )
            self._list.addItem(item)

        self._list.itemDoubleClicked.connect(self._accept_zone)
        v.addWidget(self._list)

        # 自定义通道名称
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("自定义名称："))
        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText("输入自定义通道名称（不绑定标准分区）")
        custom_row.addWidget(self._custom_edit)
        v.addLayout(custom_row)

        # 确认 / 取消
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _accept_zone(self, item: QListWidgetItem) -> None:
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        item.setSelected(True)
        self._on_accept()

    def _on_accept(self) -> None:
        # 自定义名称优先
        custom = self._custom_edit.text().strip()
        if custom:
            self.result_zone_ids = []
            self.result_zone_id = ""
            self.result_custom_name = custom
            self.accept()
            return
        # 从列表选，可多选
        selected_zone_ids = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._list.selectedItems()
            if item.flags() & Qt.ItemFlag.ItemIsEnabled
        ]
        if selected_zone_ids:
            self.result_zone_ids = selected_zone_ids
            self.result_zone_id = selected_zone_ids[0]
            self.result_custom_name = ""
            self.accept()
            return
        # 无选择
        MessageDialog("未选择", "请从列表选择一个分区，或输入自定义通道名称。", buttons=["确定"], parent=self).exec()
