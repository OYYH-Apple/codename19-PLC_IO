# IO Search Replace Advanced Options Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the current IO find/replace flow with search direction, case sensitivity, current-column scope, and selection-only scope.

**Architecture:** Keep the dialog lightweight, but add explicit option controls and expose their values through small getters/setters. Push scope and direction logic into `IoTableWidget` so both find-next and replace-all reuse the same match enumeration rules, then let `MainWindow` translate dialog state into table search options while preserving selection when the user searches only inside a selection.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

### Task 1: Lock advanced search scope behavior with failing tests

**Files:**
- Modify: `tests/test_ui_table_workflow.py`
- Modify: `src/omron_io_planner/ui/io_table_widget.py`

**Step 1: Write the failing tests**

Add tests that assert:
- backward search in current-column-only mode finds the previous match in the active column
- replace-all in selection-only mode only changes selected cells
- current-column-only and selection-only can intersect without touching out-of-scope cells

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "search_direction or current_column_only or selection_only" -q`
Expected: FAIL because the table search helpers do not support these scope options yet.

**Step 3: Write minimal implementation**

Update `src/omron_io_planner/ui/io_table_widget.py` to:
- enumerate scoped cells based on visibility, current column, and selection
- support forward/backward search direction
- preserve batch replacement through the existing undo stack while respecting scope filters

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "search_direction or current_column_only or selection_only" -q`
Expected: PASS

### Task 2: Add dialog options and wire them into MainWindow

**Files:**
- Modify: `src/omron_io_planner/ui/dialogs.py`
- Modify: `src/omron_io_planner/ui/main_window.py`
- Modify: `tests/test_ui_table_workflow.py`

**Step 1: Write the failing tests**

Add tests that assert:
- the dialog can switch between forward/backward search
- dialog-scoped current-column and selection-only replace-all respects the chosen scope
- searching within selection keeps the selection scope stable while jumping between matches

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "replace_dialog_scope or direction_backward or selection_scope" -q`
Expected: FAIL because the dialog exposes only case sensitivity today.

**Step 3: Write minimal implementation**

Update the UI to:
- add search direction controls plus scope checkboxes
- include the full option state in the find/replace context cache
- preserve existing selection when the user searches only inside selection
- reuse the same options for replace current / replace all

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "replace_dialog_scope or direction_backward or selection_scope" -q`
Expected: PASS

### Task 3: Regression verification

**Files:**
- Test: `tests/test_ui_table_workflow.py`
- Test: `tests/test_window_shell.py`

**Step 1: Run focused UI tests**

Run:
- `python -m pytest tests/test_ui_table_workflow.py -k "search_replace or search_direction or current_column_only or selection_only or replace_dialog_scope" -q`
- `python -m pytest tests/test_window_shell.py -q`

Expected: PASS

**Step 2: Run full suite**

Run: `python -m pytest -q`
Expected: PASS