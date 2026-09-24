from types import SimpleNamespace

from whisperfree.transcribe import ApiTranscriber, TranscriptionRouter
from whisperfree.config import AppConfig


class _FakeTranscriptions:
    def __init__(self, response):
        self.response = response
        self.params = None

    def create(self, **params):
        self.params = params
        return self.response


def _api(model, response=None):
    api = ApiTranscriber("sk-test", model_name=model)
    transcriptions = _FakeTranscriptions(response or SimpleNamespace(text=" hello "))
    api._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))
    return api, transcriptions


def test_gpt_transcribe_sends_terms_as_keywords_not_prompt():
    api, calls = _api("gpt-transcribe")
    result = api.transcribe(b"RIFF", prompt="Glossary: 5Point.", keywords=["5Point", "PyQt6"])
    assert calls.params["model"] == "gpt-transcribe"
    assert calls.params["extra_body"] == {"keywords": ["5Point", "PyQt6"]}
    assert "prompt" not in calls.params
    assert "language" not in calls.params
    assert result.text == "hello"


def test_gpt_transcribe_sends_language_as_languages_list():
    api, calls = _api("gpt-transcribe")
    api.transcribe(b"RIFF", language="fr")
    assert calls.params["extra_body"] == {"languages": ["fr"]}
    assert "language" not in calls.params


def test_gpt_transcribe_auto_language_and_no_terms_sends_no_extras():
    api, calls = _api("gpt-transcribe")
    api.transcribe(b"RIFF", language="auto", keywords=[])
    assert "extra_body" not in calls.params


def test_keywords_are_sanitized():
    api, calls = _api("gpt-transcribe")
    api.transcribe(b"RIFF", keywords=["<b>bold</b>", "two\nlines", "  ", "fine"])
    assert calls.params["extra_body"] == {"keywords": ["bbold/b", "two lines", "fine"]}


def test_gpt_transcribe_reads_detected_language_from_languages_list():
    api, _ = _api("gpt-transcribe", SimpleNamespace(text="Bonjour", languages=[{"code": "fr"}]))
    assert api.transcribe(b"RIFF").language == "fr"
    api, _ = _api("gpt-transcribe", SimpleNamespace(text="Hmm", languages=[]))
    assert api.transcribe(b"RIFF", language="en").language == "en"


def test_legacy_models_keep_prompt_and_single_language():
    for model in ("whisper-1", "gpt-4o-mini-transcribe"):
        api, calls = _api(model)
        api.transcribe(b"RIFF", language="de", prompt="Glossary: 5Point.", keywords=["5Point"])
        assert calls.params["prompt"] == "Glossary: 5Point."
        assert calls.params["language"] == "de"
        assert "extra_body" not in calls.params


def test_router_forwards_keywords(monkeypatch):
    config = AppConfig(api_whisper_model="gpt-transcribe", language="en")
    router = TranscriptionRouter(config)
    seen = {}

    class _Api:
        def transcribe(self, audio_bytes, language="auto", prompt="", keywords=()):
            seen.update(language=language, prompt=prompt, keywords=list(keywords))

    monkeypatch.setattr(router, "_get_api", lambda: _Api())
    router.transcribe(b"RIFF", prompt="Glossary: A.", keywords=["A"])
    assert seen == {"language": "en", "prompt": "Glossary: A.", "keywords": ["A"]}
