import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolate_config_files(monkeypatch, tmp_path):
    from whisperfree import config as config_module

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config-home")
    monkeypatch.setattr(config_module, "PROJECT_ENV_PATH", tmp_path / "project.env")
    monkeypatch.setattr(config_module, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
