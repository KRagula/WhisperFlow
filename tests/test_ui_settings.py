import os

import pytest

import whisperfree.ui.settings as settings_module
from whisperfree import startup
from whisperfree.config import AppConfig
from whisperfree.ui.settings import SettingsPage


@pytest.fixture
def env(monkeypatch, tmp_path):
    state = {"enabled": False, "fail": False, "saves": 0, "changes": 0}

    def set_enabled(enabled, value_name=startup.VALUE_NAME):
        if state["fail"]:
            raise OSError("access denied")
        state["enabled"] = enabled

    monkeypatch.setattr(startup, "is_supported", lambda: True)
    monkeypatch.setattr(startup, "is_enabled", lambda value_name=startup.VALUE_NAME: state["enabled"])
    monkeypatch.setattr(startup, "set_enabled", set_enabled)
    monkeypatch.setattr(settings_module, "list_microphones", lambda: ["Mic A", "Mic B"])
    monkeypatch.setattr(settings_module, "_ENV_FILE_PATH", tmp_path / ".env")
    monkeypatch.setattr(settings_module.QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setenv("WF_SETTINGS_TEST_KEY", "sk-original")

    config = AppConfig(api_key_env="WF_SETTINGS_TEST_KEY", mic_device_name="Mic B", language="en")

    def fake_save(*args, **kwargs):
        state["saves"] += 1

    monkeypatch.setattr(config, "save", fake_save)

    def on_change(cfg):
        state["changes"] += 1

    page = SettingsPage(config, on_change)
    return config, page, state


def test_initial_values_reflect_config(qapp, env):
    config, page, state = env
    assert page.mic_combo.currentText() == "Mic B"
    assert page.language_combo.currentData() == "en"
    assert page.overlay_toggle.isChecked() == config.overlay_enabled
    assert page.newline_toggle.isChecked() == config.append_newline
    assert page.api_key_edit.text() == "sk-original"
    assert not page.startup_toggle.isChecked()
    assert state["saves"] == 0 and state["changes"] == 0  # loading does not save


def test_toggles_apply_immediately(qapp, env):
    config, page, state = env
    page.overlay_toggle.click()
    assert config.overlay_enabled is False
    page.newline_toggle.click()
    assert config.append_newline is False
    assert state["saves"] == 2 and state["changes"] == 2


def test_mic_and_language_apply_immediately(qapp, env):
    config, page, state = env
    page.mic_combo.setCurrentIndex(page.mic_combo.findText("Mic A"))
    assert config.mic_device_name == "Mic A"
    page.mic_combo.setCurrentIndex(0)
    assert config.mic_device_name is None
    page.language_combo.setCurrentIndex(page.language_combo.findData("auto"))
    assert config.language == "auto"


def test_missing_configured_mic_falls_back_without_saving(qapp, env, monkeypatch):
    config, page, state = env
    monkeypatch.setattr(settings_module, "list_microphones", lambda: ["Mic A"])
    page.refresh_mics_button.click()
    assert page.mic_combo.currentText() == "System Default"
    assert config.mic_device_name == "Mic B"
    assert state["saves"] == 0


def test_gain_is_debounced(qapp, env):
    config, page, state = env
    page.gain_slider.setValue(60)
    assert page.gain_value_label.text() == "+6.0 dB"
    assert state["saves"] == 0
    page._commit_gain()
    assert config.input_gain_db == 6.0
    assert state["saves"] == 1


def test_startup_toggle_success(qapp, env):
    config, page, state = env
    page.startup_toggle.click()
    assert state["enabled"] is True
    assert page.startup_toggle.isChecked()


def test_startup_toggle_failure_reverts(qapp, env):
    config, page, state = env
    state["fail"] = True
    page.startup_toggle.click()
    assert state["enabled"] is False
    assert not page.startup_toggle.isChecked()


def test_startup_toggle_hidden_when_unsupported(qapp, env, monkeypatch):
    config, _page, _state = env
    monkeypatch.setattr(startup, "is_supported", lambda: False)
    page = SettingsPage(config, lambda cfg: None)
    assert page.startup_toggle.isHidden()


def test_save_api_key_requires_explicit_action(qapp, env, tmp_path):
    config, page, state = env
    page.api_key_edit.setText("sk-new")
    assert os.environ["WF_SETTINGS_TEST_KEY"] == "sk-original"
    page.save_api_button.click()
    assert os.environ["WF_SETTINGS_TEST_KEY"] == "sk-new"
    assert "WF_SETTINGS_TEST_KEY=sk-new" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert page.api_status_label.text() == "API key saved."


def test_save_blank_api_key_is_rejected(qapp, env):
    config, page, state = env
    page.api_key_edit.setText("   ")
    page.save_api_button.click()
    assert os.environ["WF_SETTINGS_TEST_KEY"] == "sk-original"
    assert page.api_status_label.text() == "Enter an API key first."


def test_shutdown_is_safe_without_running_thread(qapp, env):
    config, page, state = env
    page.shutdown()  # no thread yet
    assert page._api_test_thread is None


def test_model_picker_defaults_and_applies_immediately(qapp, env):
    config, page, state = env
    assert page.model_combo.currentData() == "gpt-transcribe"
    assert [page.model_combo.itemData(i) for i in range(page.model_combo.count())] == [
        "gpt-transcribe",
        "gpt-4o-mini-transcribe",
        "whisper-1",
    ]
    page.model_combo.setCurrentIndex(page.model_combo.findData("gpt-4o-mini-transcribe"))
    assert config.api_whisper_model == "gpt-4o-mini-transcribe"
    assert state["saves"] == 1


def test_model_picker_keeps_unlisted_model_from_config(qapp, env):
    config, _page, state = env
    config.api_whisper_model = "gpt-4o-transcribe"
    page = SettingsPage(config, lambda cfg: None)
    assert page.model_combo.currentData() == "gpt-4o-transcribe"
    assert config.api_whisper_model == "gpt-4o-transcribe"
    assert state["saves"] == 0
