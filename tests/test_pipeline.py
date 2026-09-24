from types import SimpleNamespace

import whisperfree.app as app_module
from whisperfree.app import WhisperFreeController
from whisperfree.config import AppConfig
from whisperfree.dictionary import Dictionary
from whisperfree.history import TranscriptionHistory
from whisperfree.transcribe import ApiTranscriber, TranscriptionResult


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _FakeTranscriber:
    def __init__(self, text):
        self.text = text
        self.prompts = []
        self.keywords = []

    def transcribe(self, audio_bytes, prompt="", keywords=()):
        self.prompts.append(prompt)
        self.keywords.append(list(keywords))
        return TranscriptionResult(text=self.text)


def _controller(tmp_path, text, dictionary):
    return SimpleNamespace(
        _transcriber=_FakeTranscriber(text),
        _dictionary=dictionary,
        _config=AppConfig(),
        _history=TranscriptionHistory(tmp_path / "history.jsonl"),
        toast_requested=_Signal(),
        idle_requested=_Signal(),
        history_entry_added=_Signal(),
    )


def test_pipeline_applies_dictionary_and_records_duration(tmp_path, monkeypatch):
    pasted = []
    monkeypatch.setattr(app_module, "paste_text", lambda text, **kwargs: pasted.append(text) or True)
    dictionary = Dictionary(tmp_path / "dictionary.json")
    dictionary.add_term("5Point")
    dictionary.add_replacement("five point", "5Point")
    fake = _controller(tmp_path, "I work at five point.", dictionary)

    WhisperFreeController._process_session(fake, b"RIFF", 3.0)

    assert fake._transcriber.prompts == ["Glossary: 5Point."]
    assert fake._transcriber.keywords == [["5Point"]]
    assert pasted == ["I work at 5Point."]
    [saved] = fake._history.entries()
    assert saved.text == "I work at 5Point."
    assert saved.duration == 3.0
    assert fake.history_entry_added.calls and fake.idle_requested.calls


def test_blanked_transcript_is_not_pasted(tmp_path, monkeypatch):
    pasted = []
    monkeypatch.setattr(app_module, "paste_text", lambda text, **kwargs: pasted.append(text) or True)
    dictionary = Dictionary(tmp_path / "dictionary.json")
    dictionary.add_replacement("um", "")
    fake = _controller(tmp_path, "Um.", dictionary)
    fake._transcriber.text = "um"

    WhisperFreeController._process_session(fake, b"RIFF", 1.0)

    assert pasted == []
    assert fake._history.entries() == []
    assert fake.toast_requested.calls == [("Nothing to paste", 2000)]


class _FakeTranscriptions:
    def __init__(self):
        self.params = None

    def create(self, **params):
        self.params = params
        return SimpleNamespace(text=" hello ", language="en")


def _api_with_fake_client():
    api = ApiTranscriber("sk-test", model_name="whisper-1")
    transcriptions = _FakeTranscriptions()
    api._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))
    return api, transcriptions


def test_api_transcriber_sends_prompt_when_given():
    api, transcriptions = _api_with_fake_client()
    result = api.transcribe(b"RIFF", prompt="Glossary: 5Point.")
    assert transcriptions.params["prompt"] == "Glossary: 5Point."
    assert result.text == "hello"


def test_api_transcriber_omits_empty_prompt():
    api, transcriptions = _api_with_fake_client()
    api.transcribe(b"RIFF")
    assert "prompt" not in transcriptions.params


def test_configure_app_disables_quit_on_last_window_closed(qapp):
    qapp.setQuitOnLastWindowClosed(True)
    app_module.configure_app(qapp)
    assert qapp.quitOnLastWindowClosed() is False
