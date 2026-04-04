# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
)

from omron_io_planner.export import rows_io_table_channel
from omron_io_planner.models import IoChannel, IoPoint, IoProject
from omron_io_planner.ui.data_type_delegate import DataTypeDelegate
from omron_io_planner.ui.highlight_header_view import _HighlightHeaderView
from omron_io_planner.ui.io_table_widget import IoTableWidget
from omron_io_planner.ui.main_window import MainWindow
from omron_io_planner.ui.name_completer_delegate import NameCompleterDelegate
from omron_io_planner.ui.style import app_stylesheet
from omron_io_planner.ui.zone_picker_dialog import ZonePickerDialog


def _fill_table(table: IoTableWidget, rows: int, cols: int = 6) -> None:
    table.setRowCount(rows)
    table.setColumnCount(cols)
    for row in range(rows):
        for col in range(cols):
            if table.item(row, col) is None:
                table.setItem(row, col, QTableWidgetItem(""))


def _make_window(qtbot, monkeypatch) -> MainWindow:
    monkeypatch.setattr("omron_io_planner.ui.main_window.autosave_exists", lambda: False)
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

    assert table.columnWidth(table.COL_NAME) == 60
    assert table.columnWidth(table.COL_DTYPE) == 100
    assert table.columnWidth(table.COL_ADDR) == 96
    assert table.columnWidth(table.COL_RACK) == 100
    assert table.columnWidth(table.COL_USAGE) == 78
    assert header.sectionResizeMode(table.COL_COMMENT) == header.ResizeMode.Stretch


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
    ] == ["A", "A", "A", "B", "B", "B"]


def test_single_cell_edit_uses_undo_redo(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)

    table.commit_editor_text(0, table.COL_NAME, "value")
    assert table.item(0, table.COL_NAME).text() == "value"

    table.undo()
    assert table.item(0, table.COL_NAME).text() == ""

    table.redo()
    assert table.item(0, table.COL_NAME).text() == "value"


def test_duplicate_selected_rows_copies_row_content(qtbot) -> None:
    table = IoTableWidget()
    qtbot.addWidget(table)
    _fill_table(table, 4)
    table.item(0, table.COL_NAME).setText("sensor_a")
    table.item(0, table.COL_ADDR).setText("0.00")
    table.selectRow(0)

    table.duplicate_selected_rows()

    assert table.item(1, table.COL_NAME).text() == "sensor_a"
    assert table.item(1, table.COL_ADDR).text() == "0.00"


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


def test_immersive_mode_hides_outer_chrome_and_shows_focus_bar(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]

    assert not window._recent_group.isHidden()
    assert not window._project_meta_group.isHidden()
    assert not window._copy_group.isHidden()
    assert window._editor_focus_bars[table].isHidden()
    assert not window._editor_side_panels[table].isHidden()

    window._set_immersive_mode(True)

    assert window._recent_group.isHidden()
    assert window._project_meta_group.isHidden()
    assert window._copy_group.isHidden()
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


def test_immersive_focus_bar_provides_exit_button(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    table = window._channel_tables[0]
    window._set_immersive_mode(True)
    focus_bar = window._editor_focus_bars[table]
    exit_button = next(
        (button for button in focus_bar.findChildren(QPushButton) if button.text() == "退出沉浸"),
        None,
    )

    assert exit_button is not None

    exit_button.click()

    assert not window._immersive_mode
    assert focus_bar.isHidden()


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
    assert window._recent_projects_list.item(0).text().startswith(project_a.name)

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
        window._recent_projects_list.item(index).text()
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
    window._autosave_timer.stop()
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()

    window._recent_projects_list.setCurrentRow(0)
    qtbot.mouseClick(window._recent_remove_btn, Qt.MouseButton.LeftButton)

    assert window._recent_projects_list.count() == 1
    assert "beta" in window._recent_projects_list.item(0).text().lower()


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
    window = _make_window(qtbot, monkeypatch)
    window.resize(1280, 820)
    window.show()
    window._tabs.setCurrentIndex(0)
    QApplication.processEvents()

    recent_buttons = [window._recent_open_btn, window._recent_remove_btn, window._recent_clean_btn]
    preview_buttons = window._preview_actions.findChildren(
        QPushButton,
        options=Qt.FindChildOption.FindDirectChildrenOnly,
    )

    rows = [
        (window._recent_open_btn.parentWidget(), recent_buttons),
        (window._preview_actions, preview_buttons),
    ]
    for parent, buttons in rows:
        assert parent is not None
        assert buttons
        contents = parent.contentsRect()
        assert min(button.geometry().left() for button in buttons) >= contents.left()
        assert max(button.geometry().right() for button in buttons) <= contents.right()


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


def test_channel_editor_action_buttons_use_svg_icons_without_emoji_labels(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, monkeypatch)
    editor, _table = window._make_channel_editor("CIO")
    buttons = {
        button.text(): button
        for button in editor.findChildren(QPushButton)
        if button.text() in {"添加行", "删除选中"}
    }

    assert set(buttons) == {"添加行", "删除选中"}
    for button in buttons.values():
        assert button.icon().isNull() is False


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
    assert editor.lineEdit() is not None
    assert not editor.lineEdit().hasFrame()
    assert "background-color:" in editor.styleSheet()


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

    assert hints
    assert "方向键选择建议" in hints[0]
    assert "Tab 键接受建议" not in hints[0]
