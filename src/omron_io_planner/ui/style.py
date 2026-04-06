# -*- coding: utf-8 -*-
"""
UI 样式主题（现代浅色/专业工业风）。
"""
from __future__ import annotations

# ─── 颜色令牌 ───────────────────────────────────────────────────────────────
_C = {
    "bg_window":      "#F2F5F9",
    "bg_widget":      "#FFFFFF",
    "bg_alt_row":     "#F5F8FF",
    "bg_header":      "#25364F",
    "bg_header_hover":"#31455F",
    "bg_groupbox":    "#FFFFFF",
    "bg_toolbar":     "#213147",
    "bg_tab":         "#E6ECF6",
    "bg_tab_sel":     "#FFFFFF",
    "bg_btn":         "#355F8C",
    "bg_btn_hover":   "#4272A7",
    "bg_btn_pressed": "#2B5078",
    "bg_btn_danger":  "#C0392B",
    "bg_btn_danger_h":"#E74C3C",
    "bg_input":       "#FFFFFF",
    "bg_sel":         "#355F8C",
    "bg_sel_unfocus": "#D8E3F3",
    "border":         "#D5DCEA",
    "border_focus":   "#3D6C9E",
    "fg_text":        "#1E2235",
    "fg_header":      "#FFFFFF",
    "fg_btn":         "#FFFFFF",
    "fg_label":       "#3A3F5C",
    "fg_placeholder": "#A0A8C0",
    "fg_tab":         "#4A5070",
    "fg_tab_sel":     "#2D3250",
    "accent":         "#2F668F",
    "shadow":         "rgba(0,0,0,0.08)",
    "radius":         "10px",
    "radius_sm":      "8px",
}


def app_stylesheet() -> str:
    C = _C
    return f"""
/* ── 全局 ─────────────────────────────────────────────────────── */
QWidget {{
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: {C['fg_text']};
    background-color: {C['bg_window']};
}}

/* ── 主窗口 ───────────────────────────────────────────────────── */
QMainWindow {{
    background-color: {C['bg_window']};
}}
QMainWindow#appMainWindow {{
    border: 1px solid {C['border']};
}}

/* ── 自定义标题栏 ──────────────────────────────────────────────── */
#appTitleBar {{
    background-color: {C['bg_toolbar']};
    border-bottom: 1px solid rgba(255,255,255,0.08);
}}
#appTitleBarLabel {{
    color: {C['fg_header']};
    font-size: 10pt;
    font-weight: 600;
    background: transparent;
}}
#appTitleBarMenuRow {{
    background: transparent;
}}
#appTitleBarMenuButton, #appTitleBarButton, #appTitleBarButtonDanger {{
    color: {C['fg_header']};
    background: transparent;
    border: 1px solid transparent;
    border-radius: {C['radius_sm']};
    padding: 4px 10px;
}}
#appTitleBarMenuButton {{
    min-height: 28px;
    padding: 0 22px 0 10px;
}}
#appTitleBarMenuButton::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    right: 8px;
}}
#appTitleBarMenuButton:hover, #appTitleBarButton:hover {{
    background-color: rgba(255,255,255,0.15);
    border-color: rgba(255,255,255,0.2);
}}
#appTitleBarButtonDanger:hover {{
    background-color: {C['bg_btn_danger_h']};
    border-color: rgba(255,255,255,0.12);
}}

/* ── 工具栏 ───────────────────────────────────────────────────── */
QToolBar {{
    background-color: {C['bg_toolbar']};
    border: none;
    padding: 4px 8px;
    spacing: 4px;
}}
QToolBar::separator {{
    background: rgba(255,255,255,0.45);
    width: 1px;
    margin: 6px 10px;
}}
QToolBar QToolButton {{
    color: {C['fg_header']};
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {C['radius_sm']};
    padding: 5px 10px;
    font-size: 9pt;
}}
QToolBar QToolButton:hover {{
    background-color: rgba(255,255,255,0.15);
    border-color: rgba(255,255,255,0.3);
}}
QToolBar QToolButton:pressed {{
    background-color: rgba(255,255,255,0.1);
}}
QToolBar QToolButton:checked {{
    background-color: rgba(255,255,255,0.18);
    border-color: rgba(255,255,255,0.3);
}}

/* ── GroupBox ──────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {C['bg_groupbox']};
    border: 1px solid {C['border']};
    border-radius: {C['radius']};
    margin-top: 8px;
    padding: 12px 10px 8px 10px;
    font-weight: bold;
    color: {C['fg_label']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    background-color: {C['bg_window']};
    color: {C['accent']};
    font-size: 9pt;
    font-weight: bold;
}}

/* ── 侧栏条目 ───────────────────────────────────────────────────── */
#recentProjectItemWidget {{
    background: transparent;
    border: 1px solid #D7E1F0;
    border-radius: 12px;
}}
#recentProjectItemWidget[activeProject="true"] {{
    background: transparent;
    border-color: #91B1E2;
}}
#recentProjectItemWidget[pinnedProject="true"] {{
    border-color: #B8CAE6;
}}
#recentProjectItemWidget[missingProject="true"] {{
    background: transparent;
    border-color: #E6C0B8;
}}
#recentProjectItemTextBox {{
    background: transparent;
}}
#recentProjectItemActionsBox {{
    background: transparent;
}}
#recentProjectItemTitle {{
    color: {C['fg_text']};
    font-size: 10pt;
    font-weight: 700;
    background: transparent;
}}
#recentProjectItemPath {{
    color: #5A6481;
    font-size: 8.5pt;
    background: transparent;
}}
#recentProjectItemMeta {{
    color: #56617B;
    font-size: 8pt;
    font-weight: 600;
    background: transparent;
}}

/* ── 输入框 ────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {C['bg_input']};
    border: 1px solid {C['border']};
    border-radius: {C['radius_sm']};
    padding: 4px 8px;
    color: {C['fg_text']};
    selection-background-color: {C['bg_sel']};
}}
QLineEdit:focus {{
    border-color: {C['border_focus']};
    background-color: #FAFCFF;
}}
QLineEdit::placeholder {{
    color: {C['fg_placeholder']};
}}
QPlainTextEdit {{
    background-color: {C['bg_input']};
    border: 1px solid {C['border']};
    border-radius: {C['radius_sm']};
    padding: 6px 8px;
    color: {C['fg_text']};
    selection-background-color: {C['bg_sel']};
}}
QPlainTextEdit:focus {{
    border-color: {C['border_focus']};
    background-color: #FAFCFF;
}}

/* ── 按钮 ──────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {C['bg_btn']};
    color: {C['fg_btn']};
    border: 1px solid transparent;
    border-radius: {C['radius_sm']};
    padding: 6px 14px;
    font-weight: 600;
    min-width: 72px;
}}
QPushButton[compact="true"] {{
    min-width: 0;
    padding: 6px 12px;
    font-size: 9pt;
}}
QPushButton:hover {{
    background-color: {C['bg_btn_hover']};
}}
QPushButton:pressed {{
    background-color: {C['bg_btn_pressed']};
}}
QPushButton:checked {{
    background-color: {C['bg_btn_pressed']};
}}
QPushButton:disabled {{
    background-color: #C0C4D0;
    color: #8890A0;
}}
QPushButton[danger="true"] {{
    background-color: {C['bg_btn_danger']};
}}
QPushButton[danger="true"]:hover {{
    background-color: {C['bg_btn_danger_h']};
}}
QToolButton#recentProjectActionButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {C['radius_sm']};
    padding: 3px;
}}
QToolButton#recentProjectActionButton:hover {{
    background-color: #EAF1FB;
    border-color: #C8D7EE;
}}
QToolButton#recentProjectActionButton:checked {{
    background-color: {C['bg_btn']};
    border-color: {C['bg_btn']};
}}
QToolButton#recentProjectActionButton[danger="true"]:hover {{
    background-color: #FCECE9;
    border-color: #E6B7B0;
}}
QToolButton#recentProjectActionButton[danger="true"]:checked {{
    background-color: #F7D8D4;
    border-color: #DFA49C;
}}
#mainSidebar {{
    background: transparent;
}}
#projectMetaGroup {{
    min-width: 240px;
}}
#projectMetaActionsRow {{
    background: transparent;
}}
#projectMetaCopyPanel {{
    background-color: #F8FBFF;
    border: 1px solid #D8E3F4;
    border-radius: {C['radius']};
}}
#projectMetaCopyTitle {{
    color: #244C7B;
    font-size: 8.5pt;
    font-weight: 700;
    background: transparent;
}}
#projectMetaCopyButtons {{
    background: transparent;
}}
#projectMetaCopyButtons QPushButton[compact="true"] {{
    min-width: 96px;
}}
#tabCornerActions {{
    background: transparent;
}}
#tabCornerActions QPushButton[compact="true"] {{
    min-width: 112px;
}}

/* ── 沉浸模式条 ───────────────────────────────────────────────────── */
#immersiveFocusBar {{
    background-color: #EAF0FF;
    border: 1px solid #C9D5F0;
    border-radius: {C['radius']};
}}
#immersiveModeBadge {{
    color: #244A86;
    background-color: rgba(74,111,165,0.14);
    border-radius: {C['radius_sm']};
    padding: 4px 8px;
    font-weight: 600;
}}
#editorToolsBar {{
    background: #FFFFFF;
    border: 1px solid #D8E2F0;
    border-radius: 12px;
}}
#editorToolsHeader {{
    background: transparent;
}}
#editorToolsBadge {{
    color: #244C7B;
    background-color: #E9F0FB;
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 8.5pt;
    font-weight: 700;
}}
#editorToolsSummary {{
    color: #5F6A82;
    background: transparent;
    font-size: 9pt;
}}
#editorToolsButtonsRow {{
    background: transparent;
}}
#editorToolsButtonsRow QPushButton[compact="true"] {{
    min-width: 88px;
}}
#batchEditHint {{
    color: #667189;
    background: transparent;
    border: none;
    padding: 0;
    font-size: 8.5pt;
}}
#batchEditGuideButton {{
    background-color: #EDF3FB;
    border-color: #D3E0F1;
    color: #244C7B;
    font-weight: 700;
}}
#validationHeader {{
    background: transparent;
}}
#validationSummaryLabel {{
    color: #5A6080;
    font-size: 9pt;
    background: transparent;
}}
#validationBody {{
    background: transparent;
}}
#validationBody QListWidget {{
    border-radius: 8px;
}}

/* ── TabWidget ─────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {C['border']};
    border-radius: {C['radius']};
    background-color: {C['bg_widget']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {C['bg_tab']};
    color: {C['fg_tab']};
    border: 1px solid {C['border']};
    border-bottom: none;
    border-top-left-radius: {C['radius_sm']};
    border-top-right-radius: {C['radius_sm']};
    padding: 6px 14px;
    margin-right: 2px;
    font-size: 9pt;
}}
QTabBar::tab:selected {{
    background-color: {C['bg_tab_sel']};
    color: {C['fg_tab_sel']};
    font-weight: bold;
    border-color: {C['border']};
    border-bottom-color: {C['bg_tab_sel']};
}}
QTabBar::tab:hover:!selected {{
    background-color: #C8D0E8;
}}


/* ── 表格 ──────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {C['bg_widget']};
    alternate-background-color: {C['bg_alt_row']};
    gridline-color: {C['border']};
    border: 1px solid {C['border']};
    border-radius: {C['radius_sm']};
    outline: none;
    selection-background-color: transparent;
    selection-color: {C['fg_text']};
}}
QTableWidget::item {{
    padding: 3px 6px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: transparent;
    color: {C['fg_text']};
    border: none;
}}
QTableWidget::item:focus {{
    outline: none;
    border: none;
}}
QHeaderView::section {{
    background-color: {C['bg_header']};
    color: {C['fg_header']};
    padding: 5px 8px;
    border: none;
    border-right: 1px solid rgba(255,255,255,0.15);
    font-weight: bold;
    font-size: 9pt;
}}
QHeaderView::section:hover {{
    background-color: {C['bg_header_hover']};
}}
QHeaderView::section:vertical {{
    background-color: #4A5070;
    color: {C['fg_header']};
    font-weight: normal;
    font-size: 8pt;
}}

/* ── 列表 ──────────────────────────────────────────────────────── */
QListWidget {{
    background-color: {C['bg_widget']};
    alternate-background-color: {C['bg_alt_row']};
    border: 1px solid {C['border']};
    border-radius: {C['radius_sm']};
    outline: none;
}}
QListWidget::item {{
    padding: 4px 8px;
}}
QListWidget::item:selected {{
    background-color: {C['bg_sel']};
    color: #FFFFFF;
    border-radius: 3px;
}}
QListWidget::item:hover {{
    background-color: {C['bg_sel_unfocus']};
}}
#recentProjectsGroup {{
    min-width: 240px;
}}
#recentProjectsFilterRow {{
    background: transparent;
}}
#recentProjectsList {{
    background: transparent;
    border: none;
}}
#recentProjectsList::item {{
    min-height: 88px;
    padding: 4px 0;
    background: transparent;
    border: none;
}}
#recentProjectsList::item:selected {{
    background: transparent;
    color: {C['fg_text']};
}}
#recentProjectsList::item:hover {{
    background: transparent;
}}

/* ── 下拉框 ────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {C['bg_input']};
    border: 1px solid {C['border']};
    border-radius: {C['radius_sm']};
    padding: 3px 8px;
    min-width: 80px;
}}
QComboBox:focus {{
    border-color: {C['border_focus']};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 20px;
    border-left: 1px solid {C['border']};
    border-radius: 0 {C['radius_sm']} {C['radius_sm']} 0;
}}
QComboBox QAbstractItemView {{
    background-color: {C['bg_widget']};
    border: 1px solid {C['border']};
    selection-background-color: {C['bg_sel']};
    selection-color: #FFFFFF;
    outline: none;
}}

/* ── 滚动条 ────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {C['bg_window']};
    width: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #B0B8D0;
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {C['bg_window']};
    height: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #B0B8D0;
    border-radius: 5px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C['accent']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Splitter ──────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {C['border']};
    width: 3px;
    border-radius: 2px;
}}
QSplitter::handle:hover {{
    background-color: {C['accent']};
}}

/* ── 状态栏 ────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {C['bg_toolbar']};
    color: rgba(255,255,255,0.8);
    font-size: 8pt;
    padding: 2px 8px;
}}
QStatusBar::item {{
    border: none;
}}

/* ── 自定义弹窗 ──────────────────────────────────────────────── */
#appDialogFrame {{
    background-color: {C['bg_widget']};
    border: 1px solid {C['border']};
    border-radius: 10px;
}}
#appDialogTitleBar {{
    background-color: {C['bg_toolbar']};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
#appDialogTitleLabel {{
    color: {C['fg_header']};
    font-size: 10pt;
    font-weight: 600;
    background: transparent;
}}
#appDialogCloseButton {{
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    background-color: transparent;
}}
#appDialogCloseButton:hover {{
    background-color: {C['bg_btn_danger_h']};
}}
#appDialogBody {{
    background-color: {C['bg_widget']};
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
}}
#appDialogMessage {{
    color: {C['fg_text']};
    background: transparent;
}}

/* ── Toast ────────────────────────────────────────────────────── */
#appToast {{
    background-color: rgba(45,50,80,0.96);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
}}
#appToast[toastKind="success"] {{
    background-color: rgba(46,125,90,0.96);
}}
#appToast[toastKind="error"] {{
    background-color: rgba(192,57,43,0.96);
}}
#appToastTitle {{
    color: #FFFFFF;
    font-weight: 600;
    background: transparent;
}}
#appToastMessage {{
    color: rgba(255,255,255,0.92);
    background: transparent;
}}

/* ── Loading Popup ─────────────────────────────────────────────── */
#appLoadingPopup {{
    background-color: rgba(45,50,80,0.97);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
}}
#appLoadingPopupTitle {{
    color: #FFFFFF;
    font-weight: 600;
    background: transparent;
}}
#appLoadingPopupMessage {{
    color: rgba(255,255,255,0.9);
    background: transparent;
}}

/* ── 菜单 ──────────────────────────────────────────────────────── */
QMenu {{
    background-color: {C['bg_widget']};
    border: 1px solid {C['border']};
    border-radius: {C['radius_sm']};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 24px 6px 16px;
    color: {C['fg_text']};
    border-radius: 3px;
    margin: 1px 4px;
}}
QMenu::item:selected {{
    background-color: {C['bg_sel']};
    color: #FFFFFF;
}}
QMenu::separator {{
    height: 1px;
    background-color: {C['border']};
    margin: 3px 8px;
}}

/* ── 消息框 ────────────────────────────────────────────────────── */
QMessageBox {{
    background-color: {C['bg_widget']};
}}
QMessageBox QPushButton {{
    min-width: 80px;
    padding: 5px 16px;
}}

/* ── Label ─────────────────────────────────────────────────────── */
QLabel {{
    color: {C['fg_label']};
    background-color: transparent;
}}

/* ── Tooltip ───────────────────────────────────────────────────── */
QToolTip {{
    background-color: {C['bg_header']};
    color: {C['fg_header']};
    border: 1px solid {C['accent']};
    border-radius: {C['radius_sm']};
    padding: 4px 8px;
    font-size: 9pt;
}}
"""
