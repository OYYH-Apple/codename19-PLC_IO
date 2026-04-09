# IO Search Replace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Excel-style find/replace for the current IO editor table, including find next, replace, replace all, and keyboard entry points.

**Architecture:** Keep row filtering and content search separate. Add table-level search/replace helpers to `IoTableWidget` so matching and batch replacement reuse the existing undo stack, then add a lightweight non-modal dialog in `dialogs.py` and wire it into `MainWindow` with Ctrl+F / Ctrl+H plus menu actions.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

### Task 1: Lock search/replace table behavior with failing tests

**Files:**
- Modify: `tests/test_ui_table_workflow.py`
- Modify: `src/omron_io_planner/ui/io_table_widget.py`

**Step 1: Write the failing tests**

Add tests that assert:
- `IoTableWidget.find_next_match(...)` can search from the current cell and wrap around the current table
- `replace_all_matches(...)` updates multiple cells and can be undone/redone as one batch edit
- replacing one matched occurrence only changes the matched substring, not the whole cell value

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "search_replace or find_next_match or replace_all_matches" -q`
Expected: FAIL because the table search helpers do not exist yet.

**Step 3: Write minimal implementation**

Update `src/omron_io_planner/ui/io_table_widget.py` to:
- add a search match value object/dataclass
- enumerate visible searchable matches in row/column order
- support next-match lookup with wraparound
- support single replace and replace-all through the existing undo stack

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "search_replace or find_next_match or replace_all_matches" -q`
Expected: PASS

### Task 2: Add dialog + keyboard/menu entry points with failing tests

**Files:**
- Modify: `src/omron_io_planner/ui/dialogs.py`
- Modify: `src/omron_io_planner/ui/main_window.py`
- Modify: `tests/test_ui_table_workflow.py`
- Modify: `tests/test_window_shell.py`

**Step 1: Write the failing tests**

Add tests that assert:
- Ctrl+F opens the find dialog from the active channel editor
- Ctrl+H opens replace mode
- executing find/replace from the dialog moves the selection to the matched cell and updates the project data
- the old row-filter focus shortcut no longer occupies Ctrl+F

**Step 2: Run test to verify it fails**

Run:
- `python -m pytest tests/test_ui_table_workflow.py -k "find_dialog or replace_dialog or ctrl_f or ctrl_h" -q`
- `python -m pytest tests/test_window_shell.py -k "find or replace" -q`

Expected: FAIL because the dialog and shortcut wiring do not exist.

**Step 3: Write minimal implementation**

Update the UI to:
- add a reusable `FindReplaceDialog`
- keep one window-scoped dialog instance
- wire Ctrl+F to find mode and Ctrl+H to replace mode
- keep the immersive row filter accessible through a non-conflicting action/helper
- sync successful replacements back into `IoProject`, mark modified, and refresh preview state

**Step 4: Run test to verify it passes**

Run:
- `python -m pytest tests/test_ui_table_workflow.py -k "find_dialog or replace_dialog or ctrl_f or ctrl_h" -q`
- `python -m pytest tests/test_window_shell.py -k "find or replace" -q`

Expected: PASS

### Task 3: Run focused regression verification

**Files:**
- Test: `tests/test_ui_table_workflow.py`
- Test: `tests/test_window_shell.py`

**Step 1: Run focused suites**

Run:
- `python -m pytest tests/test_ui_table_workflow.py -k "search_replace or find_dialog or replace_dialog or ctrl_f or ctrl_h or focus_current_immersive_filter" -q`
- `python -m pytest tests/test_window_shell.py -q`

Expected: PASS

**Step 2: Run full suite**

Run: `python -m pytest -q`
Expected: PASS