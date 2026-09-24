from datetime import date, datetime

from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.history import TranscriptionEntry
from whisperfree.ui import theme
from whisperfree.ui.widgets import (
    FlowLayout,
    HistoryRow,
    ToggleSwitch,
    asset_path,
    format_day,
    format_time,
)


def test_apply_theme_forces_light_palette(qapp):
    theme.apply_theme(qapp)
    palette = qapp.palette()
    assert palette.color(QtGui.QPalette.ColorRole.Window).name().upper() == theme.BACKGROUND
    assert palette.color(QtGui.QPalette.ColorRole.WindowText).name().upper() == theme.TEXT
    assert palette.color(QtGui.QPalette.ColorRole.Base).name().upper() == theme.SURFACE
    assert qapp.style().name().lower() == "fusion"


def test_stylesheet_braces_balance():
    assert theme.STYLESHEET.count("{") == theme.STYLESHEET.count("}")
    assert "#Card" in theme.STYLESHEET and "#NavButton" in theme.STYLESHEET


def test_ui_font_prefers_segoe_variable():
    font = theme.ui_font()
    assert font.families()[0] == "Segoe UI Variable Text"
    assert font.pixelSize() == 13


def test_asset_path_points_at_repo_assets():
    assert asset_path("app_icon.ico").exists()


def test_format_day_relative_labels():
    today = date(2026, 9, 24)
    assert format_day(datetime(2026, 9, 24, 9).astimezone(), today) == "Today"
    assert format_day(datetime(2026, 9, 23, 9).astimezone(), today) == "Yesterday"
    assert format_day(datetime(2026, 9, 21, 9).astimezone(), today) == "Monday, September 21"
    assert format_day(datetime(2025, 10, 19, 9).astimezone(), today) == "Sunday, October 19, 2025"


def test_format_time_drops_leading_zero():
    assert format_time(datetime(2026, 9, 24, 9, 5).astimezone()) == "9:05 AM"
    assert format_time(datetime(2026, 9, 24, 22, 38).astimezone()) == "10:38 PM"


def test_toggle_switch_toggles_on_click(qapp):
    toggle = ToggleSwitch()
    seen = []
    toggle.toggled.connect(seen.append)
    toggle.click()
    assert toggle.isChecked() and seen == [True]
    toggle.blockSignals(True)
    toggle.setChecked(False)
    toggle.blockSignals(False)
    assert not toggle.grab().isNull()  # paints without animation state
    assert toggle.sizeHint() == QtCore.QSize(36, 20)


def test_flow_layout_wraps(qapp):
    container = QtWidgets.QWidget()
    layout = FlowLayout(container, spacing=8)
    for _ in range(5):
        label = QtWidgets.QLabel("x")
        label.setFixedSize(80, 20)
        layout.addWidget(label)
    assert layout.count() == 5
    assert layout.heightForWidth(1000) == 20
    assert layout.heightForWidth(200) == 20 * 3 + 8 * 2


def test_history_row_copy(qapp):
    entry = TranscriptionEntry(timestamp=datetime(2026, 9, 24, 10).astimezone(), text="  Hello world  ", words=2)
    row = HistoryRow(entry)
    assert row.text_label.text() == "Hello world"
    row.copy_button.click()
    assert QtWidgets.QApplication.clipboard().text() == "Hello world"
    assert row.copy_button.text() == "Copied"
