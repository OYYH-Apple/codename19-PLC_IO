# Auto-Generated Names Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically derive IO names from zone prefix, address, and comment, refresh names when source fields change, and surface auto-updates with transient + persistent highlights.

**Architecture:** Add a pure helper module for name derivation so project-load normalization and table-side recalculation share the same rules. Extend `IoTableWidget` so single-cell and batch edits recompute derived names inside the existing undo flow, and let `MainWindow` normalize loaded projects plus extend validation to catch duplicate names.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt

---

### Task 1: Lock the naming rules with unit tests

**Files:**
- Create: `tests/test_auto_name.py`
- Create: `src/omron_io_planner/auto_name.py`

**Step 1: Write the failing tests**

Add unit tests that assert:
- `CIO + 0.01 + 阻挡气缸伸出` renders `CIO_0.01_阻挡气缸伸出`
- `WR + 10.00 + ""` renders `W_10.00_待注释`
- `DM + invalid-address + 阻挡气缸伸出` renders `D_待分配_阻挡气缸伸出`
- custom channels fall back to `IO`
- comment normalization converts spaces / punctuation to `_` and collapses repeats

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auto_name.py -q`
Expected: FAIL because the helper module does not exist yet.

**Step 3: Write minimal implementation**

Create `src/omron_io_planner/auto_name.py` with:
- zone-id to prefix normalization
- address normalization / fallback handling
- comment normalization / fallback handling
- project/channel/point helpers for load-time normalization

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auto_name.py -q`
Expected: PASS

### Task 2: Recompute derived names inside table edits and show highlight state

**Files:**
- Modify: `src/omron_io_planner/ui/io_table_widget.py`
- Modify: `src/omron_io_planner/ui/style.py`
- Modify: `tests/test_ui_table_workflow.py`

**Step 1: Write the failing tests**

Add UI tests that assert:
- editing comment or address overwrites the name using the derived rule
- manual edits to the name are later overwritten by address/comment edits
- generated names get a highlight marker that clears after the name cell is selected or edited
- batch changes touching address/comment recalculate all affected rows

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "auto_generated_name" -q`
Expected: FAIL because the table does not recompute names or track highlight state.

**Step 3: Write minimal implementation**

Update `IoTableWidget` to:
- accept the channel `zone_id`
- recompute derived names after edit / undo / redo / batch changes for affected rows only
- keep auto-name highlight state in item data roles plus a short flash timer
- clear persistent highlight when the name cell is focused or edited

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "auto_generated_name" -q`
Expected: PASS

### Task 3: Normalize loaded projects and validate duplicate names

**Files:**
- Modify: `src/omron_io_planner/ui/main_window.py`
- Modify: `tests/test_ui_table_workflow.py`

**Step 1: Write the failing tests**

Add UI tests that assert:
- opening a legacy project rewrites names across all channels, marks the window modified, and shows a summary toast/message count
- duplicate derived names appear in the validation issues list with a dedicated code

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "load_project_auto_generated_name or duplicate_name" -q`
Expected: FAIL because load-time normalization and duplicate-name validation do not exist.

**Step 3: Write minimal implementation**

Update `MainWindow` to:
- normalize names immediately after JSON load and before table population
- configure each `IoTableWidget` with its channel `zone_id`
- mark modified / toast only when load-time normalization changes at least one name
- extend validation with duplicate-name detection

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "load_project_auto_generated_name or duplicate_name" -q`
Expected: PASS

### Task 4: Full verification

**Files:**
- Test: `tests/test_auto_name.py`
- Test: `tests/test_ui_table_workflow.py`

**Step 1: Run targeted suites**

Run:
- `python -m pytest tests/test_auto_name.py -q`
- `python -m pytest tests/test_ui_table_workflow.py -k "auto_generated_name or load_project_auto_generated_name or duplicate_name" -q`

Expected: PASS

**Step 2: Run full suite**

Run: `python -m pytest -q`
Expected: PASS
