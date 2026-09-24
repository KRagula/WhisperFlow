import sys
import uuid

import pytest

from whisperfree import config as config_module
from whisperfree import startup
from whisperfree.config import AppConfig


def test_launch_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\WhisperFree\WhisperFree.exe")
    assert startup.launch_command() == '"C:\\Apps\\WhisperFree\\WhisperFree.exe"'


def test_launch_command_source_prefers_pythonw(monkeypatch, tmp_path):
    (tmp_path / "python.exe").write_bytes(b"")
    (tmp_path / "pythonw.exe").write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert startup.launch_command() == f'"{tmp_path / "pythonw.exe"}" "{startup.LAUNCHER_SCRIPT}"'


def test_launch_command_source_falls_back_to_python(monkeypatch, tmp_path):
    (tmp_path / "python.exe").write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert startup.launch_command() == f'"{tmp_path / "python.exe"}" "{startup.LAUNCHER_SCRIPT}"'


def test_launcher_script_exists_and_is_absolute():
    assert startup.LAUNCHER_SCRIPT.is_absolute()
    assert startup.LAUNCHER_SCRIPT.exists()


def test_resolve_api_key_reads_project_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("WF_TEST_API_KEY=from-project-env\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "PROJECT_ENV_PATH", env_file)
    monkeypatch.setenv("WF_TEST_API_KEY", "placeholder")  # records original state for undo
    monkeypatch.delenv("WF_TEST_API_KEY")
    monkeypatch.chdir(tmp_path.parent)  # CWD is not the project
    assert AppConfig(api_key_env="WF_TEST_API_KEY").resolve_api_key() == "from-project-env"


def test_unsupported_platform_is_noop(monkeypatch):
    monkeypatch.setattr(startup, "is_supported", lambda: False)
    assert startup.read_command() is None
    assert startup.is_enabled() is False
    startup.set_enabled(True)  # must not raise


@pytest.fixture
def value_name():
    name = f"WhisperFreeTest-{uuid.uuid4().hex[:8]}"
    yield name
    startup.set_enabled(False, name)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry only")
def test_registry_round_trip(value_name):
    assert not startup.is_enabled(value_name)
    startup.set_enabled(True, value_name)
    assert startup.is_enabled(value_name)
    assert startup.read_command(value_name) == startup.launch_command()
    startup.set_enabled(False, value_name)
    assert not startup.is_enabled(value_name)
    startup.set_enabled(False, value_name)  # deleting twice is fine


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry only")
def test_refresh_if_stale_rewrites_old_path(value_name):
    import winreg

    assert startup.refresh_if_stale(value_name) is False  # not enabled: nothing to do
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, startup.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, '"C:\\old\\WhisperFree.exe"')
    assert startup.refresh_if_stale(value_name) is True
    assert startup.read_command(value_name) == startup.launch_command()
    assert startup.refresh_if_stale(value_name) is False
