# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, qInstallMessageHandler
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QAbstractItemDelegate,
    QComboBox,
    QLineEdit,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
    QToolButton,
)

from omron_io_planner.export import rows_io_table_channel
from omron_io_planner.models import IoChannel, IoPoint, IoProject
from omron_io_planner.ui.data_type_delegate import DataTypeDelegate
from omron_io_planner.ui.highlight_header_view import _HighlightHeaderView
from omron_io_planner.ui.io_table_widget import IoTableWidget
from omron_io_planner.ui.main_window import MainWindow
from omron_io_planner.ui.name_completer_delegate import NameCompleterDelegate
from omron_io_planner.ui.style import app_stylesheet
from omron_io_planner.ui.zone_info_panel import ZoneInfoPanel
from omron_io_planner.ui.zone_picker_dialog import ZonePickerDialog


def _fill_table(table: IoTableWidget, rows: int, cols: int = 6) -> None:
    table.setRowCount(rows)
    table.setColumnCount(cols)
    for row in range(rows):
        for col in range(cols):
            if table.item(row, col) is None:
                table.setItem(row, col, QTableWidgetItem(""))


def _recent_item_widget_text(window: MainWindow, index: int) -> str:
    item = window._recent_projects_list.item(index)
    widget = window._recent_projects_list.itemWidget(item)
    title = widget.findChild(QLabel, "recentProjectItemTitle")
    path = widget.findChild(QLabel, "recentProjectItemPath")
    meta = widget.findChild(QLabel, "recentProjectItemMeta")
    return " ".join(
        part
        for part in (
            title.text() if title is not None else "",
            path.text() if path is not None else "",
            meta.text() if meta is not None else "",
        )
        if part
    )


def _make_window(qtbot, monkeypatch, prefs=None) -> MainWindow:
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    class _TestPrefs:
        def startup_preferences(self) -> dict[str, object]:
            return {
                "remember_window_state": False,
                "saved_window_rect": [],
                "auto_open_recent": False,
                "show_recent_sidebar": True,
            }

        def recent_workspace_preferences(self) -> dict[str, object]:
            return {"auto_prune_missing": False, "allow_pinned": True}

        def editor_defaults(self) -> dict[str, object]:
            return {}

        def recent_files(self) -> list[str]:
            return []

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return ""

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def show_recent_full_path(self) -> bool:
            return False

    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: prefs or _TestPrefs())
    window = MainWindow()
    window._confirm_discard = lambda: True
    window._autosave_timer.stop()
    qtbot.addWidget(window)
    return window


def test_rows_io_table_channel_preserves_channel_order() -> None:
    project = IoProject(
        channels=[
            IoChannel(
                "A",
                [
                    IoPoint(name="late", data_type="BOOL", address="10.00", comment="late"),
                    IoPoint(name="early", data_type="BOOL", address="0.00", comment="early"),
                ],
            )
        ]
    )

    rows = rows_io_table_channel(project, 0)

    assert [row[0] for row in rows[1:]] == ["late", "early"]


def test_table_keeps_buffer_rows_for_continuous_entry(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)

    assert table.rowCount() >= 50


def test_table_default_column_widths_match_editor_layout(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    header = table.horizontalHeader()

    assert table.columnWidth(table.COL_NAME) == 220
    assert table.columnWidth(table.COL_DTYPE) == 100
    assert table.columnWidth(table.COL_ADDR) == 96
    assert table.columnWidth(table.COL_RACK) == 100
    assert table.columnWidth(table.COL_USAGE) == 78
    assert header.sectionResizeMode(table.COL_COMMENT) == header.ResizeMode.Stretch


def test_saved_name_column_width_overrides_default(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)

    widths = [table.columnWidth(col) for col in range(table.columnCount())]
    widths[table.COL_NAME] = 104

    table.apply_layout_state({"widths": widths})

    assert table.columnWidth(table.COL_NAME) == 104


def test_single_value_paste_fills_selected_block(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.setCurrentCell(0, 0)
    table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 1), True)
    QApplication.clipboard().setText("X")

    table._paste()

    assert [table.item(row, col).text() for row in range(2) for col in range(2)] == ["X"] * 4


def test_single_row_paste_repeats_across_selected_rows(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 5)
    table.setCurrentCell(0, 0)
    table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 2, 1), True)
    QApplication.clipboard().setText("A\tB")

    table._paste()

    assert [
        table.item(row, col).text()
        for row in range(3)
        for col in range(2)
    ] == ["A", "B", "A", "B", "A", "B"]


def test_single_column_paste_repeats_across_selected_columns(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.setCurrentCell(0, 0)
    table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 2), True)
    QApplication.clipboard().setText("A\nB")

    table._paste()

    assert [
        table.item(row, col).text()
        for row in range(2)
        for col in range(3)
    ] == ["IO_待分配_待注释", "A", "A", "IO_待分配_待注释", "B", "B"]


def test_single_cell_edit_uses_undo_redo(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)

    table.commit_editor_text(0, table.COL_NAME, "value")
    assert table.item(0, table.COL_NAME).text() == "value"

    table.undo()
    assert table.item(0, table.COL_NAME).text() == ""

    table.redo()
    assert table.item(0, table.COL_NAME).text() == "value"


def test_insert_row_uses_undo_redo(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    table.item(0, table.COL_NAME).setText("row0")
    table.item(1, table.COL_NAME).setText("row1")
    table.setCurrentCell(0, table.COL_NAME)
    initial_rows = table.rowCount()

    table._insert_row(below=True)

    assert table.rowCount() == initial_rows + 1
    assert table.item(1, table.COL_NAME).text() == ""
    assert table.item(2, table.COL_NAME).text() == "row1"

    table.undo()

    assert table.rowCount() == initial_rows
    assert table.item(1, table.COL_NAME).text() == "row1"

    table.redo()

    assert table.rowCount() == initial_rows + 1
    assert table.item(1, table.COL_NAME).text() == ""
    assert table.item(2, table.COL_NAME).text() == "row1"


def test_duplicate_selected_rows_copies_row_content(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_ADDR).setText("0.00")
    table.item(0, table.COL_COMMENT).setText("sensor_a")
    table.selectRow(0)

    table.duplicate_selected_rows()

    assert table.item(1, table.COL_NAME).text() == "IO_0.00_sensor_a"
    assert table.item(1, table.COL_ADDR).text() == "0.00"


def test_duplicate_selected_rows_uses_undo_redo(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    table.item(0, table.COL_ADDR).setText("0.00")
    table.item(0, table.COL_COMMENT).setText("row0")
    table.item(1, table.COL_ADDR).setText("0.01")
    table.item(1, table.COL_COMMENT).setText("row1")
    table.selectRow(0)

    table.duplicate_selected_rows()

    assert table.item(0, table.COL_ADDR).text() == "0.00"
    assert table.item(1, table.COL_ADDR).text() == "0.00"
    assert table.item(2, table.COL_ADDR).text() == "0.01"

    table.undo()

    assert table.item(0, table.COL_ADDR).text() == "0.00"
    assert table.item(1, table.COL_ADDR).text() == "0.01"

    table.redo()

    assert table.item(0, table.COL_ADDR).text() == "0.00"
    assert table.item(1, table.COL_ADDR).text() == "0.00"
    assert table.item(2, table.COL_ADDR).text() == "0.01"


def test_delete_selected_rows_uses_undo_redo(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    table.item(0, table.COL_ADDR).setText("0.00")
    table.item(0, table.COL_COMMENT).setText("row0")
    table.item(1, table.COL_ADDR).setText("0.01")
    table.item(1, table.COL_COMMENT).setText("row1")
    table.selectRow(0)

    table._delete_selected_rows()

    assert table.item(0, table.COL_ADDR).text() == "0.01"

    table.undo()

    assert table.item(0, table.COL_ADDR).text() == "0.00"
    assert table.item(1, table.COL_ADDR).text() == "0.01"

    table.redo()

    assert table.item(0, table.COL_ADDR).text() == "0.01"


def test_fill_down_increments_trailing_numbers(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_COMMENT).setText("测试3")
    table.setCurrentCell(0, table.COL_COMMENT)
    table.setRangeSelected(QTableWidgetSelectionRange(0, table.COL_COMMENT, 2, table.COL_COMMENT), True)

    table._fill_down()

    assert table.item(1, table.COL_COMMENT).text() == "测试4"
    assert table.item(2, table.COL_COMMENT).text() == "测试5"


def test_fill_drag_continues_numeric_sequence(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 5)
    table.item(0, table.COL_COMMENT).setText("测试1")
    table.item(1, table.COL_COMMENT).setText("测试2")

    table._do_fill_drag(0, table.COL_COMMENT, 1, table.COL_COMMENT, 3)

    assert table.item(2, table.COL_COMMENT).text() == "测试3"
    assert table.item(3, table.COL_COMMENT).text() == "测试4"


def test_ctrl_d_shortcut_triggers_fill_down(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_COMMENT).setText("测试7")
    table.setCurrentCell(0, table.COL_COMMENT)
    table.setRangeSelected(QTableWidgetSelectionRange(0, table.COL_COMMENT, 2, table.COL_COMMENT), True)
    table.show()
    table.setFocus()

    qtbot.keyClick(table, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)

    assert table.item(1, table.COL_COMMENT).text() == "测试8"
    assert table.item(2, table.COL_COMMENT).text() == "测试9"


def test_tab_and_enter_shortcuts_navigate_cells(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.show()
    table.setCurrentCell(0, table.COL_NAME)
    table.setFocus()

    qtbot.keyClick(table, Qt.Key.Key_Tab)
    assert (table.currentRow(), table.currentColumn()) == (0, table.COL_DTYPE)

    qtbot.keyClick(table, Qt.Key.Key_Return)
    assert (table.currentRow(), table.currentColumn()) == (1, table.COL_DTYPE)


def test_ctrl_arrow_shortcut_jumps_to_edge_without_extending_selection(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    for column, text in ((table.COL_DTYPE, "BOOL"), (table.COL_ADDR, "0.00"), (table.COL_COMMENT, "说明")):
        table.item(1, column).setText(text)
    table.show()
    table.setCurrentCell(1, table.COL_DTYPE)
    table.setFocus()

    qtbot.keyClick(table, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)

    assert (table.currentRow(), table.currentColumn()) == (1, table.COL_COMMENT)
    assert [(index.row(), index.column()) for index in table.selectedIndexes()] == [(1, table.COL_COMMENT)]


def test_ctrl_shift_arrow_shortcut_extends_selection_to_data_edge(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    for column, text in ((table.COL_DTYPE, "BOOL"), (table.COL_ADDR, "0.00"), (table.COL_COMMENT, "说明")):
        table.item(1, column).setText(text)
    table.show()
    table.setCurrentCell(1, table.COL_DTYPE)
    table.setFocus()

    qtbot.keyClick(table, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)

    assert (table.currentRow(), table.currentColumn()) == (1, table.COL_COMMENT)
    assert [(index.row(), index.column()) for index in table.selectedIndexes()] == [
        (1, table.COL_DTYPE),
        (1, table.COL_ADDR),
        (1, table.COL_COMMENT),
    ]


def test_ctrl_end_shortcut_jumps_to_last_used_cell(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 6)
    table.item(2, table.COL_USAGE).setText("辅助")
    table.item(4, table.COL_ADDR).setText("10.00")
    table.show()
    table.setCurrentCell(0, table.COL_NAME)
    table.setFocus()

    qtbot.keyClick(table, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)

    assert (table.currentRow(), table.currentColumn()) == (4, table.COL_ADDR)
    assert [(index.row(), index.column()) for index in table.selectedIndexes()] == [(4, table.COL_ADDR)]


def test_main_window_updates_project_immediately_after_table_change(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("A", [IoPoint(name="old", data_type="BOOL", address="0.00", comment="")]),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=1)

    table = window._channel_tables[0]
    table.item(0, table.COL_NAME).setText("new")
    QApplication.processEvents()

    assert window._project.channels[0].points[0].name == "new"


def test_main_window_adds_multiple_channels_in_one_action(qtbot, monkeypatch) -> None:
    class _FakeDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, existing_zone_ids, parent=None) -> None:
            self.result_zone_ids = ["CIO", "WR"]
            self.result_custom_name = ""

        def exec(self) -> int:
            return self.DialogCode.Accepted

    monkeypatch.setattr("omron_io_planner.ui.main_window.ZonePickerDialog", _FakeDialog)
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(name="demo", channels=[IoChannel("自定义1", [])])
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=1)
    before = len(window._project.channels)

    window._add_channel()

    assert len(window._project.channels) == before + 2


def test_preview_double_click_jumps_to_source_row(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("A", [IoPoint(name="from-a", data_type="BOOL", address="0.00", comment="")]),
            IoChannel("B", [IoPoint(name="from-b", data_type="BOOL", address="1.00", comment="")]),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=0)

    preview = window._preview_table
    assert preview is not None

    item = preview.item(0, 1)
    preview.itemDoubleClicked.emit(item)

    assert window._tabs.currentIndex() == 1
    assert window._channel_tables[0].currentRow() == 0


def test_preview_sidebar_is_placed_left_of_preview_table(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    assert window._preview_sidebar is not None
    assert window._preview_actions is not None
    assert window._preview_sidebar is not window._preview_table.parentWidget()


def test_preview_table_autosizes_name_and_comment_columns_for_longest_content(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("A", [IoPoint(name="短", data_type="BOOL", address="0.00", comment="短注释")]),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=0)
    QApplication.processEvents()

    preview = window._preview_table
    assert preview is not None
    short_name_width = preview.columnWidth(1)
    short_comment_width = preview.columnWidth(4)

    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel(
                "A",
                [
                    IoPoint(
                        name="很长的名称用于验证全通道预览列宽会根据最长内容自动扩展",
                        data_type="BOOL",
                        address="0.00",
                        comment="这是一条明显更长的注释内容，用来验证预览表会在刷新后自动拉宽注释列",
                    )
                ],
            ),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=0)
    QApplication.processEvents()

    preview = window._preview_table
    assert preview is not None
    assert preview.columnWidth(1) > short_name_width
    assert preview.columnWidth(4) > short_comment_width


def test_preview_table_comment_column_clamps_and_shrinks_with_shorter_content(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    long_comment = "超长注释内容" * 80
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("A", [IoPoint(name="A", data_type="BOOL", address="0.00", comment=long_comment)]),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=0)
    QApplication.processEvents()

    preview = window._preview_table
    assert preview is not None
    long_comment_width = preview.columnWidth(4)
    assert long_comment_width <= 420

    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("A", [IoPoint(name="A", data_type="BOOL", address="0.00", comment="短注释")]),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=0)
    QApplication.processEvents()

    preview = window._preview_table
    assert preview is not None
    assert preview.columnWidth(4) < long_comment_width


def test_immersive_mode_hides_outer_chrome_and_shows_focus_bar(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    sidebar = window._project_meta_group.parentWidget()

    assert window._btn_enter_immersive is not None
    assert not window._btn_enter_immersive.isHidden()
    assert window._btn_enter_immersive.text() == "进入沉浸"
    assert sidebar is not None
    assert not sidebar.isHidden()
    assert not window._recent_group.isHidden()
    assert not window._project_meta_group.isHidden()
    assert not window._copy_group.isHidden()
    assert window._editor_focus_bars[table].isHidden()
    assert not window._editor_side_panels[table].isHidden()

    window._set_immersive_mode(True)

    assert window._recent_group.isHidden()
    assert window._project_meta_group.isHidden()
    assert window._copy_group.isHidden()
    assert sidebar.isHidden()
    assert not window._btn_enter_immersive.isHidden()
    assert window._btn_enter_immersive.text() == "退出沉浸"
    assert not window._editor_focus_bars[table].isHidden()
    assert window._editor_side_panels[table].isHidden()


def test_immersive_filter_hides_blank_rows_and_nonmatching_rows(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel(
                "CIO 区",
                [
                    IoPoint(name="阻挡气缸伸出", data_type="BOOL", address="0.00", comment="伸出到位"),
                    IoPoint(name="阻挡气缸缩回", data_type="BOOL", address="0.01", comment="缩回到位"),
                ],
                zone_id="CIO",
            )
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=1)
    table = window._channel_tables[0]

    window._set_immersive_mode(True)
    window._editor_filter_edits[table].setText("缩回")
    QApplication.processEvents()

    assert table.isRowHidden(0)
    assert not table.isRowHidden(1)
    assert table.isRowHidden(2)


def test_focus_current_immersive_filter_targets_active_table(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    editor = window._editor_filter_edits[table]
    calls: list[str] = []

    monkeypatch.setattr(editor, "setFocus", lambda: calls.append("focus"))
    monkeypatch.setattr(editor, "selectAll", lambda: calls.append("select"))

    window._set_immersive_mode(True)

    window._focus_current_editor_filter()

    assert calls == ["focus", "select"]


def test_find_next_match_wraps_from_current_cell(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_USAGE).setText("输入")
    table.item(1, table.COL_USAGE).setText("仅此一次")
    table.item(2, table.COL_USAGE).setText("输出")
    table.setCurrentCell(3, table.COL_USAGE)

    match = table.find_next_match("仅此")

    assert match is not None
    assert (match.row, match.col, match.start, match.length) == (1, table.COL_USAGE, 0, 2)


def test_find_next_match_skips_current_cell_when_current_cell_already_matches(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.item(0, table.COL_USAGE).setText("目标-当前")
    table.item(1, table.COL_USAGE).setText("目标-下一条")
    table.setCurrentCell(0, table.COL_USAGE)

    match = table.find_next_match("目标")

    assert match is not None
    assert (match.row, match.col) == (1, table.COL_USAGE)


def test_replace_match_only_updates_matched_substring_and_uses_undo(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    table.item(0, table.COL_USAGE).setText("气缸伸出到位")
    table.setCurrentCell(1, table.COL_USAGE)

    match = table.find_next_match("伸出")

    assert match is not None

    table.replace_match(match, "缩回")

    assert table.item(0, table.COL_USAGE).text() == "气缸缩回到位"

    table.undo()
    assert table.item(0, table.COL_USAGE).text() == "气缸伸出到位"

    table.redo()
    assert table.item(0, table.COL_USAGE).text() == "气缸缩回到位"


def test_replace_all_matches_batches_undo_redo(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.item(0, table.COL_COMMENT).setText("伸出到位")
    table.item(1, table.COL_COMMENT).setText("伸出报警")
    table.item(2, table.COL_NAME).setText("X_伸出")

    count = table.replace_all_matches("伸出", "缩回")

    assert count == 5
    assert table.item(0, table.COL_NAME).text().endswith("缩回到位")
    assert table.item(0, table.COL_COMMENT).text() == "缩回到位"
    assert table.item(1, table.COL_NAME).text().endswith("缩回报警")
    assert table.item(1, table.COL_COMMENT).text() == "缩回报警"
    assert table.item(2, table.COL_NAME).text() == "X_缩回"

    table.undo()
    assert table.item(0, table.COL_NAME).text().endswith("伸出到位")
    assert table.item(0, table.COL_COMMENT).text() == "伸出到位"
    assert table.item(1, table.COL_NAME).text().endswith("伸出报警")
    assert table.item(1, table.COL_COMMENT).text() == "伸出报警"
    assert table.item(2, table.COL_NAME).text() == "X_伸出"

    table.redo()
    assert table.item(0, table.COL_NAME).text().endswith("缩回到位")
    assert table.item(0, table.COL_COMMENT).text() == "缩回到位"
    assert table.item(1, table.COL_NAME).text().endswith("缩回报警")
    assert table.item(1, table.COL_COMMENT).text() == "缩回报警"
    assert table.item(2, table.COL_NAME).text() == "X_缩回"


def test_find_next_match_supports_backward_direction_in_current_column(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_COMMENT).setText("不在当前列")
    table.item(1, table.COL_USAGE).setText("目标-A")
    table.item(2, table.COL_USAGE).setText("目标-B")
    table.setCurrentCell(3, table.COL_USAGE)

    match = table.find_next_match("目标", direction="backward", current_column_only=True)

    assert match is not None
    assert (match.row, match.col) == (2, table.COL_USAGE)


def test_replace_all_matches_can_limit_to_selected_cells(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_USAGE).setText("目标")
    table.item(1, table.COL_USAGE).setText("目标")
    table.item(2, table.COL_USAGE).setText("目标")
    table.setCurrentCell(0, table.COL_USAGE)
    table.setRangeSelected(QTableWidgetSelectionRange(0, table.COL_USAGE, 1, table.COL_USAGE), True)

    count = table.replace_all_matches("目标", "完成", selected_only=True)

    assert count == 2
    assert table.item(0, table.COL_USAGE).text() == "完成"
    assert table.item(1, table.COL_USAGE).text() == "完成"
    assert table.item(2, table.COL_USAGE).text() == "目标"


def test_ctrl_f_shortcut_opens_find_dialog_for_active_editor(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    window.show()
    table.setFocus()

    qtbot.keyClick(table, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    dialog = window._find_replace_dialog

    assert dialog is not None
    assert dialog.isVisible()
    assert dialog.is_replace_mode() is False


def test_ctrl_h_shortcut_opens_replace_dialog_for_active_editor(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    window.show()
    table.setFocus()

    qtbot.keyClick(table, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    dialog = window._find_replace_dialog

    assert dialog is not None
    assert dialog.isVisible()
    assert dialog.is_replace_mode() is True


def test_replace_dialog_replace_current_updates_project(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("A", [IoPoint(name="A", data_type="BOOL", address="0.00", comment="气缸伸出到位")]),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=1)
    table = window._channel_tables[0]

    window._open_replace_dialog()
    dialog = window._find_replace_dialog

    assert dialog is not None

    dialog.set_search_text("伸出")
    dialog.set_replace_text("缩回")

    window._find_next_in_current_table()
    window._replace_current_in_current_table()
    QApplication.processEvents()

    assert table.item(0, table.COL_COMMENT).text() == "气缸缩回到位"
    assert window._project.channels[0].points[0].comment == "气缸缩回到位"


def test_find_dialog_keeps_selection_scope_while_searching(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel(
                "A",
                [
                    IoPoint(name="A", data_type="BOOL", address="0.00", comment="", usage="目标-1"),
                    IoPoint(name="B", data_type="BOOL", address="0.01", comment="", usage="目标-2"),
                    IoPoint(name="C", data_type="BOOL", address="0.02", comment="", usage="目标-3"),
                ],
            ),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=1)
    table = window._channel_tables[0]
    table.setCurrentCell(0, table.COL_USAGE)
    table.setRangeSelected(QTableWidgetSelectionRange(0, table.COL_USAGE, 1, table.COL_USAGE), True)

    window._open_find_dialog()
    dialog = window._find_replace_dialog

    assert dialog is not None

    dialog.set_search_text("目标")
    dialog.set_selected_only(True)
    window._find_next_in_current_table()
    selected_cells = sorted((index.row(), index.column()) for index in table.selectedIndexes())

    assert selected_cells == [(0, table.COL_USAGE), (1, table.COL_USAGE)]
    assert table.currentRow() == 1

    window._find_next_in_current_table()
    selected_cells = sorted((index.row(), index.column()) for index in table.selectedIndexes())

    assert selected_cells == [(0, table.COL_USAGE), (1, table.COL_USAGE)]
    assert table.currentRow() == 0


def test_replace_dialog_scope_options_limit_to_current_column_and_selection(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel(
                "A",
                [
                    IoPoint(name="A", data_type="BOOL", address="0.00", comment="目标", usage="目标"),
                    IoPoint(name="B", data_type="BOOL", address="0.01", comment="", usage="目标"),
                    IoPoint(name="C", data_type="BOOL", address="0.02", comment="", usage="目标"),
                ],
            ),
        ],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()
    window._rebuild_tabs(select_index=1)
    table = window._channel_tables[0]
    table.setCurrentCell(0, table.COL_USAGE)
    table.setRangeSelected(QTableWidgetSelectionRange(0, table.COL_USAGE, 1, table.COL_USAGE), True)

    window._open_replace_dialog()
    dialog = window._find_replace_dialog

    assert dialog is not None

    dialog.set_search_text("目标")
    dialog.set_replace_text("完成")
    dialog.set_current_column_only(True)
    dialog.set_selected_only(True)
    window._replace_all_in_current_table()
    QApplication.processEvents()

    assert table.item(0, table.COL_USAGE).text() == "完成"
    assert table.item(1, table.COL_USAGE).text() == "完成"
    assert table.item(2, table.COL_USAGE).text() == "目标"
    assert table.item(0, table.COL_COMMENT).text() == "目标"
    assert window._project.channels[0].points[0].usage == "完成"
    assert window._project.channels[0].points[1].usage == "完成"
    assert window._project.channels[0].points[2].usage == "目标"


def test_immersive_focus_bar_uses_separate_action_row_and_preserves_button_width(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    focus_bar = window._editor_focus_bars[table]

    action_row = focus_bar.findChild(type(focus_bar), "immersiveFocusActionsRow")
    buttons = action_row.findChildren(QPushButton) if action_row is not None else []

    assert action_row is not None
    assert focus_bar.layout().count() == 2
    assert buttons
    assert all(btn.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Ignored for btn in buttons)


def test_immersive_focus_bar_does_not_provide_exit_button(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    window._set_immersive_mode(True)
    focus_bar = window._editor_focus_bars[table]
    exit_button = next(
        (button for button in focus_bar.findChildren(QPushButton) if button.text() == "退出沉浸"),
        None,
    )

    assert exit_button is None


def test_tab_corner_immersive_button_enters_immersive_mode(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]

    assert window._btn_enter_immersive is not None
    assert not window._immersive_mode

    qtbot.mouseClick(window._btn_enter_immersive, Qt.MouseButton.LeftButton)

    assert window._immersive_mode
    assert window._btn_enter_immersive.text() == "退出沉浸"
    assert not window._editor_focus_bars[table].isHidden()


def test_tab_corner_immersive_button_toggles_back_after_exit(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    assert window._btn_enter_immersive is not None

    qtbot.mouseClick(window._btn_enter_immersive, Qt.MouseButton.LeftButton)
    assert window._btn_enter_immersive.text() == "退出沉浸"

    qtbot.mouseClick(window._btn_enter_immersive, Qt.MouseButton.LeftButton)

    assert not window._immersive_mode
    assert not window._btn_enter_immersive.isHidden()
    assert window._btn_enter_immersive.text() == "进入沉浸"


def test_recent_projects_sidebar_lists_and_opens_recent_files(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_b = tmp_path / "beta.json"
    project_a.write_text("{}", encoding="utf-8")
    project_b.write_text("{}", encoding="utf-8")

    class _FakePrefs:
        def recent_files(self) -> list[str]:
            return [str(project_a), str(project_b)]

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: _FakePrefs())
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    window = MainWindow()
    opened: list[str] = []
    window._confirm_discard = lambda: True
    window._autosave_timer.stop()
    monkeypatch.setattr(window, "_do_open_json", lambda path: opened.append(path))
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()

    assert window._recent_projects_list is not None
    assert window._recent_projects_list.count() == 2
    assert window._recent_projects_list.item(0).text() == ""
    assert project_a.name in _recent_item_widget_text(window, 0)

    item_rect = window._recent_projects_list.visualItemRect(window._recent_projects_list.item(1))
    qtbot.mouseClick(window._recent_projects_list.viewport(), Qt.MouseButton.LeftButton, pos=item_rect.center())

    assert opened == [str(project_b)]


def test_recent_project_click_and_activation_do_not_double_open(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_a.write_text("{}", encoding="utf-8")

    class _FakePrefs:
        def recent_files(self) -> list[str]:
            return [str(project_a)]

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def recent_limit(self) -> int:
            return 10

        def show_recent_full_path(self) -> bool:
            return False

    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: _FakePrefs())
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    times = iter((100.0, 100.7))
    monkeypatch.setattr("omron_io_planner.ui.main_window.time.monotonic", lambda: next(times))
    window = MainWindow()
    opened: list[str] = []
    window._confirm_discard = lambda: True
    window._autosave_timer.stop()
    monkeypatch.setattr(window, "_do_open_json", lambda path: opened.append(path))
    qtbot.addWidget(window)

    item = window._recent_projects_list.item(0)
    window._recent_projects_list.itemClicked.emit(item)
    QApplication.processEvents()
    window._recent_projects_list.itemActivated.emit(item)
    QApplication.processEvents()

    assert opened == [str(project_a)]


def test_open_recent_uses_status_loading_feedback_without_popup(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_a.write_text("{}", encoding="utf-8")
    window = _make_window(qtbot, monkeypatch)
    seen: list[tuple[str, str, bool]] = []
    window.show()
    QApplication.processEvents()

    def _fake_open(path: str) -> None:
        seen.append((window.statusBar().currentMessage(), path, QApplication.overrideCursor() is not None))

    monkeypatch.setattr(window, "_do_open_json", _fake_open)

    window._open_recent(str(project_a))
    QApplication.processEvents()

    assert seen == [(f"正在加载 {project_a.name}...", str(project_a.resolve()), True)]
    assert window._loading_popup is None or not window._loading_popup.isVisible()


def test_suspend_visible_updates_disables_visible_rebuild_subtree_and_restores_after(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window.show()
    QApplication.processEvents()

    central = window.centralWidget()
    tabs = window._tabs

    assert central is not None
    assert tabs is not None
    assert window.updatesEnabled() is True
    assert central.updatesEnabled() is True
    assert tabs.updatesEnabled() is True

    seen: list[tuple[bool, bool, bool]] = []

    with window._suspend_visible_updates():
        seen.append((window.updatesEnabled(), central.updatesEnabled(), tabs.updatesEnabled()))

    assert seen == [(False, False, False)]
    assert window.updatesEnabled() is True
    assert central.updatesEnabled() is True
    assert tabs.updatesEnabled() is True


def test_suspend_visible_updates_restores_after_exception(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window.show()
    QApplication.processEvents()

    central = window.centralWidget()
    tabs = window._tabs

    assert central is not None
    assert tabs is not None

    raised = False
    try:
        with window._suspend_visible_updates():
            assert window.updatesEnabled() is False
            assert central.updatesEnabled() is False
            assert tabs.updatesEnabled() is False
            raise RuntimeError("boom")
    except RuntimeError:
        raised = True

    assert raised is True
    assert window.updatesEnabled() is True
    assert central.updatesEnabled() is True
    assert tabs.updatesEnabled() is True


def test_rebuild_tabs_runs_inside_visual_update_suspension(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    calls: list[str] = []

    class _Guard:
        def __enter__(self):
            calls.append("enter")
            return None

        def __exit__(self, exc_type, exc, tb):
            calls.append("exit")
            return False

    monkeypatch.setattr(window, "_suspend_visible_updates", lambda: _Guard())

    window._project = IoProject(
        name="demo",
        channels=[IoChannel("CIO 区", [IoPoint(name="X", data_type="BOOL", address="0.00", comment="")], zone_id="CIO")],
    )
    window._channel_tables.clear()
    window._sync_meta_from_project()

    window._rebuild_tabs(select_index=1)

    assert calls == ["enter", "exit"]


def test_load_project_auto_generated_name_marks_window_modified_and_shows_summary(qtbot, monkeypatch, tmp_path) -> None:
    project_path = tmp_path / "legacy.json"
    project_path.write_text("{}", encoding="utf-8")
    window = _make_window(qtbot, monkeypatch)
    seen: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        "omron_io_planner.ui.main_window.load_project_json",
        lambda path: IoProject(
            name="demo",
            channels=[
                IoChannel(
                    "CIO 区",
                    [IoPoint(name="旧名称", data_type="BOOL", address="0.01", comment="阻挡气缸伸出")],
                    zone_id="CIO",
                )
            ],
        ),
    )
    monkeypatch.setattr(window, "_show_toast", lambda title, text, kind="info": seen.append((title, text, kind)))

    window._do_open_json(str(project_path))

    assert window._project.channels[0].points[0].name == "CIO_0.01_阻挡气缸伸出"
    assert window._channel_tables[0].item(0, window._channel_tables[0].COL_NAME).text() == "CIO_0.01_阻挡气缸伸出"
    assert window._modified is True
    assert seen == [("自动名称", "已自动更新 1 个名称", "info")]


def test_recent_projects_sidebar_filters_items(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_b = tmp_path / "beta.json"
    project_a.write_text("{}", encoding="utf-8")
    project_b.write_text("{}", encoding="utf-8")

    class _FakePrefs:
        def recent_files(self) -> list[str]:
            return [str(project_a), str(project_b)]

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def recent_limit(self) -> int:
            return 10

        def show_recent_full_path(self) -> bool:
            return False

    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: _FakePrefs())
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    window = MainWindow()
    window._confirm_discard = lambda: True
    window._autosave_timer.stop()
    qtbot.addWidget(window)

    filter_edit = window._recent_filter_edit
    assert isinstance(filter_edit, QLineEdit)

    filter_edit.setText("beta")
    QApplication.processEvents()

    visible = [
        _recent_item_widget_text(window, index)
        for index in range(window._recent_projects_list.count())
        if not window._recent_projects_list.item(index).isHidden()
    ]
    assert len(visible) == 1
    assert "beta" in visible[0].lower()


def test_recent_projects_sidebar_remove_button_updates_list(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_b = tmp_path / "beta.json"
    project_a.write_text("{}", encoding="utf-8")
    project_b.write_text("{}", encoding="utf-8")

    class _FakePrefs:
        def __init__(self) -> None:
            self.paths = [str(project_a), str(project_b)]

        def recent_files(self) -> list[str]:
            return list(self.paths)

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            self.paths = [value for value in self.paths if value != path]

        def clear_recent(self) -> None:
            self.paths = []

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def recent_limit(self) -> int:
            return 10

        def show_recent_full_path(self) -> bool:
            return False

    prefs = _FakePrefs()
    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: prefs)
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    window = MainWindow()
    window._confirm_discard = lambda: True
    window._dialog_message = lambda *args, **kwargs: "移除"  # type: ignore[method-assign]
    window._autosave_timer.stop()
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()

    window._recent_projects_list.setCurrentRow(0)
    item = window._recent_projects_list.currentItem()
    assert item is not None
    widget = window._recent_projects_list.itemWidget(item)
    assert widget is not None
    remove_button = next(
        button
        for button in widget.findChildren(QToolButton)
        if button.toolTip() == "移除最近项目"
    )
    qtbot.mouseClick(remove_button, Qt.MouseButton.LeftButton)

    assert window._recent_projects_list.count() == 1
    assert "beta" in _recent_item_widget_text(window, 0).lower()


def test_recent_projects_remove_button_respects_cancel(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_a.write_text("{}", encoding="utf-8")

    class _FakePrefs:
        def __init__(self) -> None:
            self.paths = [str(project_a)]

        def recent_files(self) -> list[str]:
            return list(self.paths)

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            self.paths = [value for value in self.paths if value != path]

        def clear_recent(self) -> None:
            self.paths = []

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def recent_limit(self) -> int:
            return 10

        def show_recent_full_path(self) -> bool:
            return False

    prefs = _FakePrefs()
    monkeypatch.setattr("omron_io_planner.ui.main_window.get_prefs", lambda: prefs)
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
    window = MainWindow()
    window._confirm_discard = lambda: True
    window._dialog_message = lambda *args, **kwargs: "取消"  # type: ignore[method-assign]
    window._autosave_timer.stop()
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()

    item = window._recent_projects_list.item(0)
    assert item is not None
    widget = window._recent_projects_list.itemWidget(item)
    assert widget is not None
    remove_button = next(
        button
        for button in widget.findChildren(QToolButton)
        if button.toolTip() == "移除最近项目"
    )

    qtbot.mouseClick(remove_button, Qt.MouseButton.LeftButton)

    assert window._recent_projects_list.count() == 1
    assert prefs.paths == [str(project_a)]


def test_preview_sidebar_action_buttons_have_uniform_width(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window.resize(1280, 820)
    window.show()
    window._tabs.setCurrentIndex(0)
    QApplication.processEvents()

    buttons = window._preview_actions.findChildren(QPushButton)
    widths = [button.width() for button in buttons]

    assert len(buttons) == 3
    assert max(widths) - min(widths) <= 1


def test_sidebar_action_buttons_fit_within_available_width(qtbot, monkeypatch) -> None:
    class _RecentPrefs:
        def startup_preferences(self) -> dict[str, object]:
            return {
                "remember_window_state": False,
                "saved_window_rect": [],
                "auto_open_recent": False,
                "show_recent_sidebar": True,
            }

        def recent_workspace_preferences(self) -> dict[str, object]:
            return {"auto_prune_missing": False, "allow_pinned": True}

        def editor_defaults(self) -> dict[str, object]:
            return {}

        def recent_files(self) -> list[str]:
            return ["C:/tmp/recent-a.json"]

        def recent_projects(self) -> list[dict[str, object]]:
            return [
                {
                    "path": "C:/tmp/recent-a.json",
                    "pinned": False,
                    "last_opened": 0.0,
                    "last_saved": 0.0,
                }
            ]

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return ""

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def show_recent_full_path(self) -> bool:
            return False

    window = _make_window(qtbot, monkeypatch, prefs=_RecentPrefs())
    window.resize(1280, 820)
    window.show()
    window._tabs.setCurrentIndex(0)
    QApplication.processEvents()

    recent_item = window._recent_projects_list.item(0)
    assert recent_item is not None
    recent_widget = window._recent_projects_list.itemWidget(recent_item)
    assert recent_widget is not None
    recent_buttons = recent_widget.findChildren(QToolButton)
    path_label = recent_widget.findChild(QLabel, "recentProjectItemPath")
    meta_label = recent_widget.findChild(QLabel, "recentProjectItemMeta")
    clean_button = window._recent_clean_btn
    preview_buttons = window._preview_actions.findChildren(
        QPushButton,
        options=Qt.FindChildOption.FindDirectChildrenOnly,
    )

    rows = [
        (recent_widget, recent_buttons),
        (window._preview_actions, preview_buttons),
    ]
    for parent, buttons in rows:
        assert parent is not None
        assert buttons
        contents = parent.contentsRect()
        assert min(button.geometry().left() for button in buttons) >= contents.left()
        assert max(button.geometry().right() for button in buttons) <= contents.right()

    assert isinstance(clean_button, QToolButton)
    assert clean_button.parentWidget().objectName() == "recentProjectsFilterRow"
    assert len(recent_buttons) == 2
    assert all(button.width() <= 32 for button in recent_buttons)
    assert path_label is not None and path_label.text()
    assert meta_label is not None and meta_label.isVisible() and meta_label.text()
    assert recent_item.background().style() == Qt.BrushStyle.NoBrush
    assert recent_item.sizeHint().height() >= 88


def test_copy_group_is_separate_from_project_meta_group(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    assert window._copy_group is not None
    assert window._project_meta_group is not None
    assert not window._project_meta_group.isAncestorOf(window._copy_group)


def test_project_meta_group_sits_above_recent_group_in_sidebar(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    assert window._project_meta_group is not None
    assert window._recent_group is not None
    sidebar = window._project_meta_group.parentWidget()

    assert sidebar is not None
    assert sidebar is window._recent_group.parentWidget()

    sidebar_layout = sidebar.layout()
    assert sidebar_layout is not None
    assert sidebar_layout.indexOf(window._project_meta_group) < sidebar_layout.indexOf(window._recent_group)


def test_channel_management_buttons_live_in_tab_corner_widget(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    assert window._tabs is not None
    corner = window._tabs.cornerWidget(Qt.Corner.TopRightCorner)

    assert corner is not None
    assert corner.isAncestorOf(window._btn_enter_immersive)
    assert corner.isAncestorOf(window._btn_add_ch)
    assert corner.isAncestorOf(window._btn_del_ch)
    assert not window._project_meta_group.isAncestorOf(window._btn_enter_immersive)
    assert not window._project_meta_group.isAncestorOf(window._btn_add_ch)
    assert not window._project_meta_group.isAncestorOf(window._btn_del_ch)


def test_recent_project_card_shows_meta_state_and_roomier_item_height(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_a.write_text("{}", encoding="utf-8")

    class _RecentPrefs:
        def startup_preferences(self) -> dict[str, object]:
            return {
                "remember_window_state": False,
                "saved_window_rect": [],
                "auto_open_recent": False,
                "show_recent_sidebar": True,
            }

        def recent_workspace_preferences(self) -> dict[str, object]:
            return {"auto_prune_missing": False, "allow_pinned": True}

        def editor_defaults(self) -> dict[str, object]:
            return {}

        def recent_files(self) -> list[str]:
            return [str(project_a)]

        def recent_projects(self) -> list[dict[str, object]]:
            return [
                {
                    "path": str(project_a),
                    "pinned": True,
                    "last_opened": 0.0,
                    "last_saved": 0.0,
                }
            ]

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def show_recent_full_path(self) -> bool:
            return False

    window = _make_window(qtbot, monkeypatch, prefs=_RecentPrefs())
    window.show()
    QApplication.processEvents()

    recent_item = window._recent_projects_list.item(0)
    assert recent_item is not None
    recent_widget = window._recent_projects_list.itemWidget(recent_item)
    assert recent_widget is not None

    meta_label = recent_widget.findChild(QLabel, "recentProjectItemMeta")

    assert meta_label is not None
    assert meta_label.isVisible()
    assert "已置顶" in meta_label.text()
    assert recent_item.sizeHint().height() >= 88


def test_recent_project_item_uses_widget_only_without_fallback_item_text(qtbot, monkeypatch, tmp_path) -> None:
    project_a = tmp_path / "alpha.json"
    project_a.write_text("{}", encoding="utf-8")

    class _RecentPrefs:
        def startup_preferences(self) -> dict[str, object]:
            return {
                "remember_window_state": False,
                "saved_window_rect": [],
                "auto_open_recent": False,
                "show_recent_sidebar": True,
            }

        def recent_workspace_preferences(self) -> dict[str, object]:
            return {"auto_prune_missing": False, "allow_pinned": True}

        def editor_defaults(self) -> dict[str, object]:
            return {}

        def recent_files(self) -> list[str]:
            return [str(project_a)]

        def recent_projects(self) -> list[dict[str, object]]:
            return [
                {
                    "path": str(project_a),
                    "pinned": False,
                    "last_opened": 0.0,
                    "last_saved": 0.0,
                }
            ]

        def autosave_enabled(self) -> bool:
            return False

        def autosave_interval(self) -> int:
            return 120

        def add_recent(self, path) -> None:  # noqa: ANN001
            pass

        def remove_recent(self, path) -> None:  # noqa: ANN001
            pass

        def clear_recent(self) -> None:
            pass

        def last_dir(self) -> str:
            return str(tmp_path)

        def set_last_dir(self, path) -> None:  # noqa: ANN001
            pass

        def show_recent_full_path(self) -> bool:
            return False

    window = _make_window(qtbot, monkeypatch, prefs=_RecentPrefs())
    window.show()
    QApplication.processEvents()

    recent_item = window._recent_projects_list.item(0)

    assert recent_item.text() == ""
    assert recent_item.data(Qt.ItemDataRole.UserRole + 2)


def test_channel_editor_uses_consistent_spacing_without_splitter(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)

    editor, _table = window._make_channel_editor("CIO")
    layout = editor.layout()

    assert layout is not None
    assert layout.spacing() >= 10
    assert not editor.findChildren(QSplitter)


def test_copy_buttons_use_svg_icons_without_emoji_labels(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    banned = "📋🗑🔄📥📤🆕📂💾＋－"
    buttons = [
        window._btn_copy_io,
        window._btn_copy_sym,
        window._btn_copy_d,
        window._btn_copy_cio,
        window._btn_copy_all,
    ]

    assert all(button is not None for button in buttons)
    for button in buttons:
        assert button.icon().isNull() is False
        assert not any(ch in banned for ch in button.text())


def test_recent_project_card_style_uses_transparent_background() -> None:
    stylesheet = app_stylesheet()

    assert "#recentProjectItemWidget {" in stylesheet
    assert "background: transparent;" in stylesheet


def test_channel_editor_action_buttons_use_svg_icons_without_emoji_labels(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    editor, _table = window._make_channel_editor("CIO")
    buttons = [
        button.text()
        for button in editor.findChildren(QPushButton)
        if button.text() == "添加行"
    ]

    assert buttons == []


def test_zone_picker_dialog_accepts_multiple_selected_zones(qtbot, monkeypatch) -> None:
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", lambda *args, **kwargs: None)
    dialog = ZonePickerDialog(existing_zone_ids=set())
    qtbot.addWidget(dialog)

    first = dialog._list.item(0)
    second = dialog._list.item(1)
    first.setSelected(True)
    second.setSelected(True)

    dialog._on_accept()

    assert dialog.result_zone_ids == [
        first.data(Qt.ItemDataRole.UserRole),
        second.data(Qt.ItemDataRole.UserRole),
    ]


def test_table_keeps_fill_handle_but_disables_row_dragging(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.show()
    table.setCurrentCell(0, 0)
    table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 1), True)

    assert not table.dragEnabled()
    assert not table.acceptDrops()
    assert table.dragDropMode() == table.DragDropMode.NoDragDrop
    assert table._handle_rect() is not None


def test_table_selection_uses_header_border_color() -> None:
    table = IoTableWidget()

    assert table._selection_border_color().name() == _HighlightHeaderView.COL_HEADER_BORDER.name()


def test_table_single_click_does_not_enter_edit_mode(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    table.show()

    item = table.item(0, 0)
    qtbot.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(item).center())

    assert table.state() != QAbstractItemView.State.EditingState


def test_vertical_header_click_selects_entire_row(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.show()
    QApplication.processEvents()

    header = table.verticalHeader()
    pos = QPoint(header.width() // 2, header.sectionPosition(1) + header.sectionSize(1) // 2)

    qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=pos)

    assert {index.row() for index in table.selectedIndexes()} == {1}
    assert len(table.selectedIndexes()) == table.columnCount()


def test_vertical_header_drag_selects_multiple_rows(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 6)
    table.show()
    QApplication.processEvents()

    header = table.verticalHeader()
    x_pos = header.width() // 2
    start = QPoint(x_pos, header.sectionPosition(1) + header.sectionSize(1) // 2)
    end = QPoint(x_pos, header.sectionPosition(3) + header.sectionSize(3) // 2)

    qtbot.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(header.viewport(), pos=end)
    qtbot.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=end)

    assert {index.row() for index in table.selectedIndexes()} == {1, 2, 3}


def test_double_click_editor_is_frameless_inline(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    table.show()

    item = table.item(0, 0)
    table.editItem(item)
    QApplication.processEvents()
    editor = QApplication.focusWidget()

    assert editor is not None
    assert hasattr(editor, "hasFrame")
    assert not editor.hasFrame()
    assert "border: none" in editor.styleSheet()
    assert "background-color:" in editor.styleSheet()
    assert "background: transparent" not in editor.styleSheet()


def test_data_type_editor_is_frameless_inline(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    delegate = DataTypeDelegate(table)

    editor = delegate.createEditor(
        table.viewport(), None, table.model().index(0, table.COL_DTYPE)
    )

    assert editor is not None
    assert "border: none" in editor.styleSheet()
    assert editor.isEditable() is False
    assert "background-color:" in editor.styleSheet()


def test_data_type_delegate_commits_without_view_warning(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window.show()
    QApplication.processEvents()

    table = window._channel_tables[0]
    item = table.item(0, table.COL_DTYPE)
    assert item is not None

    messages: list[str] = []

    def _handler(_mode, _context, message):  # noqa: ANN001
        messages.append(message)

    previous = qInstallMessageHandler(_handler)
    try:
        table.setCurrentItem(item)
        table.editItem(item)
        QApplication.processEvents()
        combos = [combo for combo in table.findChildren(QComboBox) if combo.parent() == table.viewport()]
        assert combos
        combo = combos[-1]
        combo.setCurrentIndex(combo.findText("INT"))
        table.closeEditor(combo, QAbstractItemDelegate.EndEditHint.SubmitModelCache)
        QApplication.processEvents()
    finally:
        qInstallMessageHandler(previous)

    assert table.item(0, table.COL_DTYPE).text() == "INT"
    assert not any("editor that does not belong to this view" in message for message in messages)


def test_data_type_delegate_ignores_late_signal_after_editor_closed(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window.show()
    QApplication.processEvents()

    table = window._channel_tables[0]
    item = table.item(0, table.COL_DTYPE)
    assert item is not None

    messages: list[str] = []

    def _handler(_mode, _context, message):  # noqa: ANN001
        messages.append(message)

    previous = qInstallMessageHandler(_handler)
    try:
        table.setCurrentItem(item)
        table.editItem(item)
        QApplication.processEvents()
        combos = [combo for combo in table.findChildren(QComboBox) if combo.parent() == table.viewport()]
        assert combos
        combo = combos[-1]
        table.closeEditor(combo, QAbstractItemDelegate.EndEditHint.SubmitModelCache)
        QApplication.processEvents()
        combo.setCurrentIndex((combo.currentIndex() + 1) % combo.count())
        QApplication.processEvents()
    finally:
        qInstallMessageHandler(previous)

    assert not any("editor that does not belong to this view" in message for message in messages)


def test_comment_delegate_suggests_opposite_phrase(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.item(0, table.COL_COMMENT).setText("阻挡气缸伸出")
    delegate = NameCompleterDelegate(table, table, source_column=table.COL_COMMENT)
    editor = delegate.createEditor(table.viewport(), None, table.model().index(1, table.COL_COMMENT))

    delegate._update_suggestion(editor, "阻挡气缸")
    completer = editor.completer()

    assert completer is not None
    assert completer.completionMode() == completer.CompletionMode.PopupCompletion
    assert not completer.popup().alternatingRowColors()
    assert "background-color: #FFFFFF" in completer.popup().styleSheet()
    assert "QListView::item:selected {" in completer.popup().styleSheet()
    assert "background-color: #355F8C;" in completer.popup().styleSheet()
    assert "color: #FFFFFF;" in completer.popup().styleSheet()
    suggestions = [
        completer.model().index(row, 0).data()
        for row in range(completer.model().rowCount())
    ]
    assert suggestions[0] == "阻挡气缸缩回"

    delegate._apply_completion(editor, "阻挡气缸缩回")

    assert editor.text() == "阻挡气缸缩回"


def test_comment_delegate_prefers_action_pair_inside_compound_phrase(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.item(0, table.COL_COMMENT).setText("阻挡气缸伸出到位")
    delegate = NameCompleterDelegate(table, table, source_column=table.COL_COMMENT)

    suggestions = delegate._suggestions_for_text("阻挡气缸")

    assert suggestions[0] == "阻挡气缸缩回到位"


def test_comment_delegate_does_not_apply_first_suggestion_without_explicit_pick(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.item(0, table.COL_COMMENT).setText("阻挡气缸伸出")
    delegate = NameCompleterDelegate(table, table, source_column=table.COL_COMMENT)
    editor = delegate.createEditor(table.viewport(), None, table.model().index(1, table.COL_COMMENT))
    qtbot.addWidget(editor)
    editor.show()
    editor.setFocus()
    editor.setText("阻挡气缸")

    delegate._update_suggestion(editor, "阻挡气缸")
    popup = editor.completer().popup()

    assert not popup.currentIndex().isValid()
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert editor.text() == "阻挡气缸"


def test_comment_delegate_applies_suggestion_after_explicit_keyboard_pick(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.item(0, table.COL_COMMENT).setText("阻挡气缸伸出")
    delegate = NameCompleterDelegate(table, table, source_column=table.COL_COMMENT)
    editor = delegate.createEditor(table.viewport(), None, table.model().index(1, table.COL_COMMENT))
    qtbot.addWidget(editor)
    editor.show()
    editor.setFocus()
    editor.setText("阻挡气缸")

    delegate._update_suggestion(editor, "阻挡气缸")
    qtbot.keyClick(editor, Qt.Key.Key_Down)
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert editor.text() == "阻挡气缸缩回"


def test_app_stylesheet_disables_table_focus_outline() -> None:
    stylesheet = app_stylesheet()

    assert "QTableWidget {" in stylesheet
    assert "outline: none;" in stylesheet
    assert "QTableWidget::item:focus" in stylesheet


def test_clicking_address_header_toggles_sort_direction(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_NAME).setText("A")
    table.item(1, table.COL_NAME).setText("B")
    table.item(2, table.COL_NAME).setText("C")
    table.item(0, table.COL_ADDR).setText("0.05")
    table.item(1, table.COL_ADDR).setText("0.01")
    table.item(2, table.COL_ADDR).setText("0.03")
    table.show()
    QApplication.processEvents()

    header = table.horizontalHeader()
    def _header_pos() -> QPoint:
        return QPoint(
            header.sectionViewportPosition(table.COL_ADDR) + header.sectionSize(table.COL_ADDR) // 2,
            header.height() // 2,
        )

    qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=_header_pos())
    asc = [table.item(row, table.COL_ADDR).text() for row in range(3)]

    qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=_header_pos())
    desc = [table.item(row, table.COL_ADDR).text() for row in range(3)]

    assert asc == ["0.01", "0.03", "0.05"]
    assert desc == ["0.05", "0.03", "0.01"]


def test_channel_shortcut_hint_matches_current_shortcuts(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    hints = [
        label.text()
        for label in window.findChildren(type(window._status_hint))
        if "快捷键速查" in label.text()
    ]

    assert hints == []


def test_channel_editor_side_panel_keeps_only_zone_info_panel(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    side_panel = window._editor_side_panels[table]

    assert side_panel.findChildren(ZoneInfoPanel)
    assert side_panel.findChildren(QPushButton, "batchEditGuideButton") == []
    assert [
        button.text()
        for button in side_panel.findChildren(QPushButton)
        if button.text() in {"添加行", "删除选中"}
    ] == []


def test_continuous_entry_seeds_next_row_from_previous_values(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.set_zone_id("CIO")
    table.set_editor_defaults(
        {
            "continuous_entry": True,
            "auto_increment_address": True,
            "inherit_data_type": True,
            "inherit_rack": True,
            "inherit_usage": True,
            "auto_increment_name": True,
            "auto_increment_comment": True,
        }
    )
    table.item(0, table.COL_NAME).setText("X01")
    table.item(0, table.COL_DTYPE).setText("BOOL")
    table.item(0, table.COL_ADDR).setText("0.00")
    table.item(0, table.COL_COMMENT).setText("阻挡气缸伸出1")
    table.item(0, table.COL_RACK).setText("R1")
    table.item(0, table.COL_USAGE).setText("输入")
    table.setCurrentCell(0, table.COL_NAME)

    table._navigate(1, 0)

    assert table.item(1, table.COL_NAME).text() == "CIO_0.01_阻挡气缸伸出2"
    assert table.item(1, table.COL_ADDR).text() == "0.01"
    assert table.item(1, table.COL_COMMENT).text() == "阻挡气缸伸出2"
    assert table.item(1, table.COL_DTYPE).text() == "BOOL"
    assert table.item(1, table.COL_RACK).text() == "R1"
    assert table.item(1, table.COL_USAGE).text() == "输入"


def _prepare_continuous_entry_chain(table: IoTableWidget, *, rows: int = 4) -> None:
    _fill_table(table, rows)
    table.set_zone_id("CIO")
    table.set_editor_defaults(
        {
            "continuous_entry": True,
            "auto_increment_address": True,
            "inherit_data_type": True,
            "inherit_rack": True,
            "inherit_usage": True,
            "auto_increment_name": True,
            "auto_increment_comment": True,
        }
    )
    table.item(0, table.COL_NAME).setText("X01")
    table.item(0, table.COL_DTYPE).setText("BOOL")
    table.item(0, table.COL_ADDR).setText("0.00")
    table.item(0, table.COL_COMMENT).setText("中专1")
    table.item(0, table.COL_RACK).setText("R1")
    table.item(0, table.COL_USAGE).setText("输入")
    table.setCurrentCell(0, table.COL_NAME)
    table._navigate(1, 0)
    table._navigate(1, 0)


def test_continuous_entry_reflows_auto_filled_segment_after_source_edit(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _prepare_continuous_entry_chain(table)

    assert table.item(1, table.COL_COMMENT).text() == "中专2"
    assert table.item(2, table.COL_COMMENT).text() == "中专3"

    table.commit_editor_text(0, table.COL_COMMENT, "中转1")

    assert table.item(1, table.COL_COMMENT).text() == "中转2"
    assert table.item(2, table.COL_COMMENT).text() == "中转3"
    assert table.item(1, table.COL_NAME).text() == "CIO_0.01_中转2"
    assert table.item(2, table.COL_NAME).text() == "CIO_0.02_中转3"


def test_continuous_entry_stops_reflow_at_first_manually_edited_row(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _prepare_continuous_entry_chain(table)

    table.commit_editor_text(1, table.COL_COMMENT, "人工确认2")
    table.commit_editor_text(0, table.COL_COMMENT, "中转1")

    assert table.item(1, table.COL_COMMENT).text() == "人工确认2"
    assert table.item(1, table.COL_NAME).text() == "CIO_0.01_人工确认2"
    assert table.item(2, table.COL_COMMENT).text() == "人工确认3"
    assert table.item(2, table.COL_NAME).text() == "CIO_0.02_人工确认3"


def test_continuous_entry_clears_auto_filled_segment_when_source_loses_pattern(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _prepare_continuous_entry_chain(table)

    table.commit_editor_text(0, table.COL_COMMENT, "人工文本")

    assert table.item(1, table.COL_COMMENT).text() == ""
    assert table.item(2, table.COL_COMMENT).text() == ""
    assert table.item(1, table.COL_NAME).text() == "CIO_0.01_待注释"
    assert table.item(2, table.COL_NAME).text() == "CIO_0.02_待注释"


def test_duplicate_rows_do_not_inherit_continuous_entry_auto_state(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _prepare_continuous_entry_chain(table)

    table.setCurrentCell(1, table.COL_COMMENT)
    table.selectRow(1)
    table.duplicate_selected_rows()
    table.commit_editor_text(0, table.COL_COMMENT, "中转1")

    assert table.item(1, table.COL_COMMENT).text() == "中转2"
    assert table.item(2, table.COL_COMMENT).text() == "中专2"
    assert table.item(3, table.COL_COMMENT).text() == "中专3"


def test_sorting_preserves_continuous_entry_auto_state(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _prepare_continuous_entry_chain(table)

    table._sort_rows_by_address(Qt.SortOrder.AscendingOrder)
    table.commit_editor_text(0, table.COL_COMMENT, "中转1")

    assert table.item(1, table.COL_COMMENT).text() == "中转2"
    assert table.item(2, table.COL_COMMENT).text() == "中转3"


def test_delete_undo_preserves_continuous_entry_auto_state(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _prepare_continuous_entry_chain(table)

    table.setCurrentCell(1, table.COL_COMMENT)
    table.selectRow(1)
    table._delete_selected_rows()
    table.undo()
    table.commit_editor_text(0, table.COL_COMMENT, "中转1")

    assert table.item(1, table.COL_COMMENT).text() == "中转2"
    assert table.item(2, table.COL_COMMENT).text() == "中转3"


def test_auto_generated_name_updates_from_address_and_comment(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    table.set_zone_id("CIO")

    table.commit_editor_text(0, table.COL_ADDR, "0.01")
    table.commit_editor_text(0, table.COL_COMMENT, "阻挡气缸伸出")

    assert table.item(0, table.COL_NAME).text() == "CIO_0.01_阻挡气缸伸出"


def test_auto_generated_name_overwrites_manual_name_on_next_source_change(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    table.set_zone_id("CIO")
    table.commit_editor_text(0, table.COL_ADDR, "0.01")
    table.commit_editor_text(0, table.COL_COMMENT, "阻挡气缸伸出")
    table.commit_editor_text(0, table.COL_NAME, "手动修改名称")

    table.commit_editor_text(0, table.COL_COMMENT, "阻挡气缸缩回")

    assert table.item(0, table.COL_NAME).text() == "CIO_0.01_阻挡气缸缩回"


def test_auto_generated_name_marks_flash_then_attention_and_clears_on_selection(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    table.set_zone_id("CIO")

    table.commit_editor_text(0, table.COL_ADDR, "0.01")
    table.commit_editor_text(0, table.COL_COMMENT, "阻挡气缸伸出")

    name_item = table.item(0, table.COL_NAME)
    assert bool(name_item.data(table.ROLE_AUTO_NAME_FLASH))
    assert bool(name_item.data(table.ROLE_AUTO_NAME_ATTENTION))

    qtbot.wait(table.AUTO_NAME_FLASH_DURATION_MS + 50)

    assert not bool(name_item.data(table.ROLE_AUTO_NAME_FLASH))
    assert bool(name_item.data(table.ROLE_AUTO_NAME_ATTENTION))

    table.setCurrentCell(0, table.COL_NAME)
    QApplication.processEvents()

    assert not bool(name_item.data(table.ROLE_AUTO_NAME_ATTENTION))


def test_auto_generated_name_recomputes_after_batch_changes(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.set_zone_id("WR")

    table.apply_multi_changes(
        [
            (0, table.COL_ADDR, "", "10.00"),
            (0, table.COL_COMMENT, "", "顶升气缸伸出"),
            (1, table.COL_ADDR, "", "10.01"),
            (1, table.COL_COMMENT, "", ""),
        ],
        "批量生成",
        "generate",
    )

    assert table.item(0, table.COL_NAME).text() == "W_10.00_顶升气缸伸出"
    assert table.item(1, table.COL_NAME).text() == "W_10.01_待注释"


def test_batch_generate_rows_creates_address_sequence_and_updates_project(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]

    window._apply_batch_generate(
        table,
        {
            "start_address": "0.10",
            "row_count": 3,
            "data_type": "BOOL",
            "name_template": "X{n:02}",
            "comment_template": "阻挡气缸[伸出|缩回]到位",
            "rack": "R2",
            "usage": "输出",
        },
    )

    assert table.item(0, table.COL_NAME).text() == "CIO_0.10_阻挡气缸伸出到位"
    assert table.item(1, table.COL_NAME).text() == "CIO_0.11_阻挡气缸缩回到位"
    assert table.item(0, table.COL_ADDR).text() == "0.10"
    assert table.item(2, table.COL_ADDR).text() == "0.12"
    assert table.item(0, table.COL_COMMENT).text() == "阻挡气缸伸出到位"
    assert table.item(1, table.COL_COMMENT).text() == "阻挡气缸缩回到位"
    assert window._project.channels[0].points[2].usage == "输出"


def test_batch_edit_hint_is_visible_in_editor_shell(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]

    batch_hint = table.parentWidget().findChild(QLabel, "batchEditHint")
    guide_button = table.parentWidget().findChild(QPushButton, "batchEditGuideButton")

    assert batch_hint is not None
    assert "点左侧行号可选整行" in batch_hint.text()
    assert "Ctrl+Z" in batch_hint.text()
    assert guide_button is not None
    assert guide_button.toolTip()
    assert guide_button.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Ignored


def test_batch_edit_guide_button_opens_help(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    guide_button = table.parentWidget().findChild(QPushButton, "batchEditGuideButton")
    seen: dict[str, str] = {}

    def _fake_dialog(title: str, text: str, buttons=("确定",)):  # noqa: ANN001
        seen["title"] = title
        seen["text"] = text
        return "知道了"

    window._dialog_message = _fake_dialog  # type: ignore[method-assign]

    assert guide_button is not None

    qtbot.mouseClick(guide_button, Qt.MouseButton.LeftButton)

    assert seen["title"] == "批量编辑说明"
    assert "批量生成" in seen["text"]
    assert "Ctrl+Z" in seen["text"]


def test_bulk_row_update_and_text_transform_apply_to_selection(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 3)
    table.item(0, table.COL_NAME).setText("S1")
    table.item(1, table.COL_NAME).setText("S2")
    table.item(0, table.COL_COMMENT).setText("顶升")
    table.item(1, table.COL_COMMENT).setText("阻挡")
    table.setCurrentCell(0, 0)
    table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, table.columnCount() - 1), True)

    table.bulk_update_selected_rows({"data_type": "INT", "rack": "R5", "usage": "输出"})

    table.clearSelection()
    table.setRangeSelected(QTableWidgetSelectionRange(0, table.COL_COMMENT, 1, table.COL_COMMENT), True)
    table.bulk_transform_selection("prefix", "前缀-")

    assert table.item(0, table.COL_DTYPE).text() == "INT"
    assert table.item(1, table.COL_RACK).text() == "R5"
    assert table.item(0, table.COL_USAGE).text() == "输出"
    assert table.item(0, table.COL_COMMENT).text() == "前缀-顶升"
    assert table.item(1, table.COL_COMMENT).text() == "前缀-阻挡"


def test_comment_delegate_includes_phrase_library_suggestions(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 2)
    table.set_phrase_library([], ["阻挡气缸缩回到位", "阻挡气缸伸出到位"])
    delegate = NameCompleterDelegate(table, table, source_column=table.COL_COMMENT)

    suggestions = delegate._suggestions_for_text("阻挡气缸")

    assert suggestions[:2] == ["阻挡气缸伸出到位", "阻挡气缸缩回到位"]


def test_workspace_state_restores_preview_order_filters_and_immersive_mode(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project.workspace_state = {
        "active_tab": "WR 区",
        "preview_order": ["WR 区", "CIO 区"],
        "preview_checked": ["WR 区"],
        "immersive_mode": True,
        "filters": {"WR 区": {"query": "缩回", "filled_only": True}},
        "table_layout": {"widths": [72, 98, 104, 480, 110, 84]},
    }
    window._project.channels = [
        IoChannel("CIO 区", [IoPoint(name="A", data_type="BOOL", address="0.00", comment="")], zone_id="CIO"),
        IoChannel("WR 区", [IoPoint(name="B", data_type="BOOL", address="100.00", comment="缩回")], zone_id="WR"),
    ]
    window._channel_tables.clear()
    window._rebuild_tabs(select_index=1)

    assert window._tabs.currentIndex() == 2
    assert window._immersive_mode is True
    assert window._preview_list.item(0).text() == "WR 区"
    assert window._preview_list.item(0).checkState() == Qt.CheckState.Checked
    assert window._preview_list.item(1).checkState() == Qt.CheckState.Unchecked
    table = window._channel_tables[1]
    assert window._editor_filter_edits[table].text() == "缩回"
    assert window._editor_filled_toggles[table].isChecked() is True
    assert table.columnWidth(table.COL_ADDR) == 104


def test_validation_collects_core_issues_without_cross_zone_duplicate_address(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("CIO 区", [IoPoint(name="", data_type="BOOL", address="0.00", comment="")], zone_id="CIO"),
            IoChannel("WR 区", [IoPoint(name="A", data_type="UNKNOWN", address="0.00", comment="")], zone_id="WR"),
        ],
    )
    window._channel_tables.clear()
    window._rebuild_tabs(select_index=0)
    for index in range(window._preview_list.count()):
        window._preview_list.item(index).setCheckState(Qt.CheckState.Unchecked)

    issues = window._collect_validation_issues()

    codes = {issue["code"] for issue in issues}
    assert {"invalid_data_type", "empty_preview"} <= codes
    assert "duplicate_address" not in codes
    assert "missing_name" not in codes
    assert window._validation_group is not None
    assert window._validation_header is not None
    assert window._validation_body is not None


def test_validation_collects_duplicate_address_within_same_zone(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel(
                "WR 区",
                [
                    IoPoint(name="W_0.00_A", data_type="BOOL", address="0.00", comment=""),
                    IoPoint(name="W_0.00_B", data_type="BOOL", address="0.00", comment=""),
                ],
                zone_id="WR",
            ),
        ],
    )

    issues = window._collect_validation_issues()

    duplicate_addresses = [issue for issue in issues if issue["code"] == "duplicate_address"]
    assert len(duplicate_addresses) == 1
    assert duplicate_addresses[0]["message"] == "WR 区 / 第 2 行地址重复：0.00"


def test_validation_does_not_collect_duplicate_address_across_custom_channels(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("自定义A", [IoPoint(name="A", data_type="BOOL", address="0.00", comment="")]),
            IoChannel("自定义B", [IoPoint(name="B", data_type="BOOL", address="0.00", comment="")]),
        ],
    )

    issues = window._collect_validation_issues()

    assert "duplicate_address" not in {issue["code"] for issue in issues}


def test_validation_collects_duplicate_address_within_same_custom_channel(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel(
                "自定义A",
                [
                    IoPoint(name="A", data_type="BOOL", address="0.00", comment=""),
                    IoPoint(name="B", data_type="BOOL", address="0.00", comment=""),
                ],
            ),
            IoChannel("自定义B", [IoPoint(name="C", data_type="BOOL", address="0.00", comment="")]),
        ],
    )

    issues = window._collect_validation_issues()

    duplicate_addresses = [issue for issue in issues if issue["code"] == "duplicate_address"]
    assert len(duplicate_addresses) == 1
    assert duplicate_addresses[0]["message"] == "自定义A / 第 2 行地址重复：0.00"


def test_validation_collects_duplicate_name_issue(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._project = IoProject(
        name="demo",
        channels=[
            IoChannel("CIO 区", [IoPoint(name="CIO_0.00_阻挡气缸伸出", data_type="BOOL", address="0.00", comment="伸出")], zone_id="CIO"),
            IoChannel("WR 区", [IoPoint(name="CIO_0.00_阻挡气缸伸出", data_type="BOOL", address="10.00", comment="缩回")], zone_id="WR"),
        ],
    )

    issues = window._collect_validation_issues()
    window._refresh_validation_panel()

    assert "duplicate_name" in {issue["code"] for issue in issues}
    assert window._validation_toggle_btn is not None
    assert window._validation_summary_label is not None
    assert window._validation_body.isHidden()
    assert not window._validation_summary_label.isHidden()
    assert window._validation_list.maximumHeight() <= 112
    qtbot.mouseClick(window._validation_header, Qt.MouseButton.LeftButton)
    assert not window._validation_body.isHidden()
    assert window._validation_summary_label.isHidden()
