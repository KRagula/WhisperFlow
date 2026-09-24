from datetime import datetime

import pytest

import whisperfree.ui.settings as settings_module
from whisperfree import startup
from whisperfree.config import AppConfig
from whisperfree.dictionary import Dictionary
from whisperfree.history import TranscriptionEntry, TranscriptionHistory
from whisperfree.ui import ControlPanelWindow
from whisperfree.ui.window import NAV_ITEMS, nav_icon


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(startup, "is_supported", lambda: True)
    monkeypatch.setattr(startup, "is_enabled", lambda value_name=startup.VALUE_NAME: False)
    monkeypatch.setattr(settings_module, "list_microphones", lambda: [])
    config = AppConfig()
    monkeypatch.setattr(config, "save", lambda *a, **k: None)
    history = TranscriptionHistory(tmp_path / "history.jsonl")
    history.add_entry("First note")
    return ControlPanelWindow(
        config=config,
        on_save=lambda cfg: None,
        history=history,
        dictionary=Dictionary(tmp_path / "dictionary.json"),
    )


def test_starts_on_home(window):
    assert window.current_page_key() == "home"
    assert window.home_page.recent_count() == 1


def test_navigation_switches_pages(window):
    for key, _label in NAV_ITEMS:
        window.navigate_to(key)
        assert window.current_page_key() == key


def test_view_all_opens_history(window):
    window.home_page.view_all_button.click()
    assert window.current_page_key() == "history"


def test_new_entries_reach_home_and_history(window):
    entry = TranscriptionEntry(timestamp=datetime.now().astimezone(), text="Second note", words=2)
    window.handle_history_entry(entry)
    assert window.home_page.recent_count() == 2
    assert window.history_page.matching_count() == 2


def test_nav_icons_render(qapp):
    for key, _label in NAV_ITEMS:
        assert not nav_icon(key).isNull()
