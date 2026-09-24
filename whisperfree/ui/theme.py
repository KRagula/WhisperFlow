"""Light theme: palette constants and the global control panel stylesheet."""

from __future__ import annotations

from PyQt6 import QtGui, QtWidgets


BACKGROUND = "#F7F7F8"
SURFACE = "#FFFFFF"
SURFACE_HOVER = "#F2F2F5"
BORDER = "#E6E6EA"
BORDER_STRONG = "#D4D4DA"
TEXT = "#1C1B22"
TEXT_SECONDARY = "#6B6A75"
TEXT_MUTED = "#9A99A3"
ACCENT = "#4332D8"
ACCENT_HOVER = "#3727B7"
ACCENT_SOFT = "#EEECFC"
DANGER = "#C93636"

FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]
BASE_FONT_PX = 13


STYLESHEET = f"""
QMainWindow {{ background: {BACKGROUND}; }}

QFrame#Sidebar {{ background: {BACKGROUND}; border: none; border-right: 1px solid {BORDER}; }}
QLabel#AppName {{ font-size: 17px; font-weight: 600; color: {TEXT}; }}
QLabel#SidebarFooter {{ font-size: 12px; color: {TEXT_MUTED}; }}
QPushButton#NavButton {{
    background: transparent; border: none; border-radius: 8px;
    padding: 8px 12px; text-align: left;
    font-size: 13px; font-weight: 500; color: {TEXT_SECONDARY};
}}
QPushButton#NavButton:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; }}
QPushButton#NavButton:checked {{ background: {ACCENT_SOFT}; color: {ACCENT}; font-weight: 600; }}

QLabel#PageTitle {{ font-size: 26px; font-weight: 600; color: {TEXT}; }}
QLabel#PageSubtitle {{ font-size: 13px; color: {TEXT_SECONDARY}; }}
QLabel#SectionTitle {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#SettingTitle {{ font-size: 13px; font-weight: 600; color: {TEXT}; }}
QLabel#Body {{ font-size: 13px; color: {TEXT}; }}
QLabel#Caption {{ font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel#Muted {{ font-size: 12px; color: {TEXT_MUTED}; }}
QLabel#DayHeader {{ font-size: 12px; font-weight: 600; color: {TEXT_MUTED}; padding-top: 12px; }}
QLabel#StatValue {{ font-size: 24px; font-weight: 600; color: {TEXT}; }}
QLabel#StatusError {{ font-size: 12px; color: {DANGER}; }}
QLabel#StatusOk {{ font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel#RuleMatch {{ font-size: 13px; font-weight: 600; color: {TEXT}; }}

QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#HintBanner {{ background: {ACCENT_SOFT}; border: none; border-radius: 10px; }}
QLabel#HintText {{ font-size: 13px; font-weight: 500; color: {ACCENT}; }}
QFrame#HistoryRow {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#HistoryRow:hover {{ border-color: {BORDER_STRONG}; }}
QFrame#Divider {{ background: {BORDER}; border: none; min-height: 1px; max-height: 1px; }}

QPushButton#PrimaryButton {{
    background: {ACCENT}; color: #FFFFFF; border: none; border-radius: 8px;
    padding: 7px 16px; font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#PrimaryButton:disabled {{ background: {BORDER_STRONG}; }}
QPushButton#SecondaryButton {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 6px 14px; font-weight: 500;
}}
QPushButton#SecondaryButton:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#SecondaryButton:disabled {{ color: {TEXT_MUTED}; }}
QPushButton#GhostButton, QPushButton#DangerGhostButton {{
    background: transparent; color: {TEXT_SECONDARY}; border: none; border-radius: 6px;
    padding: 4px 8px; font-size: 12px; font-weight: 500;
}}
QPushButton#GhostButton:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; }}
QPushButton#DangerGhostButton:hover {{ background: {SURFACE_HOVER}; color: {DANGER}; }}
QPushButton#LinkButton {{ background: transparent; border: none; padding: 0; color: {ACCENT}; font-weight: 600; }}
QPushButton#LinkButton:hover {{ color: {ACCENT_HOVER}; }}

QLineEdit, QComboBox {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 6px 10px; min-height: 20px;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER}; outline: none;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
}}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG};
    width: 16px; height: 16px; margin: -7px 0; border-radius: 8px;
}}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_SECONDARY}; border: none;
    border-bottom: 2px solid transparent; padding: 8px 14px; margin-right: 4px; font-weight: 500;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

QFrame#Chip {{ background: {ACCENT_SOFT}; border: none; border-radius: 12px; }}
QLabel#ChipText {{ color: {ACCENT}; font-weight: 500; }}
QPushButton#ChipRemove {{ background: transparent; border: none; color: {ACCENT}; font-weight: 700; padding: 0 2px; }}
QPushButton#ChipRemove:hover {{ color: {DANGER}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 3px; min-height: 32px; margin: 2px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def ui_font() -> QtGui.QFont:
    """Base font for the control panel."""
    font = QtGui.QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(BASE_FONT_PX)
    return font


def build_palette() -> QtGui.QPalette:
    """Light palette so Windows dark mode never leaks into the app."""
    role = QtGui.QPalette.ColorRole
    palette = QtGui.QPalette()
    colours = {
        role.Window: BACKGROUND,
        role.WindowText: TEXT,
        role.Base: SURFACE,
        role.AlternateBase: BACKGROUND,
        role.Text: TEXT,
        role.Button: SURFACE,
        role.ButtonText: TEXT,
        role.ToolTipBase: SURFACE,
        role.ToolTipText: TEXT,
        role.PlaceholderText: TEXT_MUTED,
        role.Highlight: ACCENT,
        role.HighlightedText: "#FFFFFF",
        role.BrightText: "#FFFFFF",
        role.Link: ACCENT,
    }
    for colour_role, value in colours.items():
        palette.setColor(colour_role, QtGui.QColor(value))
    disabled = QtGui.QPalette.ColorGroup.Disabled
    for colour_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(disabled, colour_role, QtGui.QColor(TEXT_MUTED))
    return palette


def apply_theme(app: QtWidgets.QApplication) -> None:
    """Use Fusion with a fixed light palette app-wide (message boxes, tray menu, panel)."""
    app.setStyle("Fusion")
    app.setPalette(build_palette())
