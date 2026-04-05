# UI Layout Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the main window layout so the recent-project area is cleaner, the project header no longer crowds channel actions, and tab-level channel controls live in the top-right action area shown in the spec image.

**Architecture:** Keep the existing PySide6 stack and fix the layout structure instead of layering more fixed-width widgets. Move channel actions out of the project metadata form into a dedicated tab-corner action host, keep clipboard/export actions in the metadata block, and enrich the recent-project card so the sidebar reads as an intentional panel instead of a squeezed list row.

**Tech Stack:** Python 3.10+, PySide6, pytest, pytest-qt

---

### Task 1: Lock the new UI contract with failing tests

**Files:**
- Modify: `tests/test_ui_table_workflow.py`

**Step 1: Write the failing test**

Add tests that assert:
- the add/delete channel buttons are mounted in the tab widget corner area instead of inside the project metadata group
- the recent-project card exposes a visible metadata line for pinned/active/missing state and keeps its widget sizing aligned with the visual card layout

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "tab_corner or recent_project_card" -q`
Expected: FAIL because the channel buttons still live in the metadata row and the recent item metadata line is empty.

**Step 3: Write minimal implementation**

Move the channel buttons into a dedicated `QTabWidget` corner widget and populate recent-project metadata text from entry state.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "tab_corner or recent_project_card" -q`
Expected: PASS

### Task 2: Reflow the metadata and tab action layout

**Files:**
- Modify: `src/omron_io_planner/ui/main_window.py`
- Modify: `src/omron_io_planner/ui/style.py`

**Step 1: Write the failing test**

Extend the UI layout tests to assert the copy/export panel remains inside the project metadata group while the tab-corner action host is present and aligned.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "copy_group or tab_corner" -q`
Expected: FAIL if the new corner host or ancestry rules are not satisfied.

**Step 3: Write minimal implementation**

Restructure the metadata section to keep only project fields plus the copy/export panel, and style the tab-corner buttons as the primary channel management entry point.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "copy_group or tab_corner" -q`
Expected: PASS

### Task 3: Polish the recent-project card and verify full workflow

**Files:**
- Modify: `src/omron_io_planner/ui/main_window.py`
- Modify: `src/omron_io_planner/ui/style.py`
- Test: `tests/test_ui_table_workflow.py`

**Step 1: Write the failing test**

Add or update assertions for recent-project card spacing, metadata visibility, and action-button containment after resize.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "recent_projects or sidebar_action_buttons" -q`
Expected: FAIL until the card sizing and metadata rendering match the new layout.

**Step 3: Write minimal implementation**

Tune card spacing, button placement, and sidebar styling without changing app behavior.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui_table_workflow.py -k "recent_projects or sidebar_action_buttons" -q`
Expected: PASS

### Task 4: Run targeted regression verification

**Files:**
- Test: `tests/test_ui_table_workflow.py`
- Test: `tests/test_window_shell.py`

**Step 1: Run focused UI suites**

Run:
- `python -m pytest tests/test_ui_table_workflow.py -q`
- `python -m pytest tests/test_window_shell.py -q`

Expected: PASS with no regressions in existing window-shell or recent-project workflows.
