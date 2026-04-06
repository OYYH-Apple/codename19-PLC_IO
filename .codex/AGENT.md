# Codex Development Guide

## Scope
- This file defines the default engineering and UI standards for this repository.
- Any future UI change must follow these rules before adding new controls, panels, or styles.

## Product Priorities
- Prioritize IO editing speed, clarity, and low cognitive load.
- Prefer fewer, clearer controls over dense toolbars or stacked helper text.
- Every new interaction must reduce a real editing pain point, not just expose another option.

## UI Direction
- Visual direction: industrial, precise, calm, bright.
- Use clean white or soft neutral surfaces with one controlled accent family.
- Avoid muddy color mixes, accidental gradients, random highlight colors, or heavy shadows.
- Avoid decorative noise. If a surface does not improve hierarchy, remove it.

## Layout Rules
- Do not let buttons compress into unreadable pills or blank blocks.
- Long horizontal action groups must either wrap intentionally, split into rows, or collapse into secondary actions.
- File paths, timestamps, and metadata must be elided, not allowed to overlap or force ugly line breaks.
- Sidebar cards must have consistent height, spacing, padding, and action alignment.
- Lists with embedded widgets must reserve enough item height for their content.

## Typography Rules
- Build clear text hierarchy:
  - section title
  - control label
  - primary value
  - helper text
- Helper text must be short and secondary. Never dump instructions into dense paragraphs when a dedicated help action is better.
- Avoid multi-line wrapping for path-like content unless the layout is explicitly designed for it.

## Icon Rules
- Do not use emoji as icons anywhere in the app.
- If an icon is needed, add an SVG asset under `src/omron_io_planner/ui/assets/icons`.
- Icons must be visually consistent in stroke weight, size, and alignment.
- Text-only controls are preferred over weak or misleading icons.

## Interaction Rules
- High-frequency actions must stay visible and obvious.
- Secondary help belongs in tooltips, inline guidance, or a compact help dialog, not in oversized permanent blocks.
- Destructive actions must stay visually distinct.
- Selection, hover, focus, and active states must be visible but restrained.

## Recent Projects Rules
- Recent project rows are cards, not text dumps.
- Each row should show:
  - project name
  - one elided path line
  - one compact metadata line
- Row actions must live on the right edge and use compact SVG icon buttons.
- Global list actions should stay in the list header/filter row, not in a crowded footer button strip.

## Editor Toolbar Rules
- Editing toolbars must be grouped by intent, not by implementation detail.
- Primary batch actions should fit in one readable row at common laptop widths.
- If guidance is needed, provide a dedicated help entry and concise inline summary.
- Never rely on layout compression to make a crowded toolbar fit.

## Validation Panel Rules
- Validation UI must be collapsible.
- Collapsed state should keep a compact summary of current issues.
- The panel must never visually dominate the editing area when expanded.

## Implementation Rules
- Reuse existing widgets and style primitives when possible, but redesign structure when the current structure is the source of the problem.
- Prefer dynamic properties and stylesheet targets over ad hoc inline `setStyleSheet` calls.
- For custom item widgets, handle resize and text elision explicitly.
- When changing UI layout, update widget tests to cover:
  - visibility
  - button sizing
  - overflow prevention
  - core interaction behavior

## Definition of Done For UI Work
- No overlapping text.
- No clipped primary button labels.
- No emoji icons.
- No unexplained helper blocks.
- Core screens remain readable at the default launch size.
- Existing tests pass, and new UI regressions have test coverage.
