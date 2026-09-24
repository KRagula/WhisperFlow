import json

from whisperfree.config import CONFIG_VERSION, AppConfig, load_config


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_default_model_is_gpt_transcribe():
    assert AppConfig().api_whisper_model == "gpt-transcribe"


def test_old_whisper_1_config_is_migrated(tmp_path):
    path = tmp_path / "config.json"
    write(path, {"version": 3, "api_whisper_model": "whisper-1", "language": "en"})
    config = load_config(path)
    assert config.api_whisper_model == "gpt-transcribe"
    assert config.language == "en"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["api_whisper_model"] == "gpt-transcribe"
    assert saved["version"] == CONFIG_VERSION


def test_other_model_choices_are_kept_on_upgrade(tmp_path):
    path = tmp_path / "config.json"
    write(path, {"version": 3, "api_whisper_model": "gpt-4o-mini-transcribe"})
    assert load_config(path).api_whisper_model == "gpt-4o-mini-transcribe"


def test_whisper_1_chosen_after_migration_is_respected(tmp_path):
    path = tmp_path / "config.json"
    write(path, {"version": CONFIG_VERSION, "api_whisper_model": "whisper-1"})
    assert load_config(path).api_whisper_model == "whisper-1"
