from types import SimpleNamespace

from clipengine import transcribe


class _FakeWhisperModelSuccess:
    def __init__(self, model_size, device=None, compute_type=None):
        pass

    def transcribe(self, path):
        segments = [
            SimpleNamespace(start=0.0, end=2.0, text=" hola "),
            SimpleNamespace(start=2.5, end=5.0, text="mundo"),
        ]
        info = SimpleNamespace(language="es")
        return segments, info


class _FakeWhisperModelRaises:
    def __init__(self, model_size, device=None, compute_type=None):
        pass

    def transcribe(self, path):
        raise RuntimeError("modelo corrupto")


def test_transcribe_audio_returns_none_when_not_installed(monkeypatch):
    monkeypatch.setattr(transcribe, "WhisperModel", None)
    result = transcribe.transcribe_audio("audio.wav", "small", "cpu", "int8")
    assert result is None


def test_transcribe_audio_success(monkeypatch):
    monkeypatch.setattr(transcribe, "WhisperModel", _FakeWhisperModelSuccess)
    result = transcribe.transcribe_audio("audio.wav", "small", "cpu", "int8")

    assert result is not None
    assert result.language == "es"
    assert len(result.segments) == 2
    assert result.segments[0].text == "hola"
    assert result.text == "hola mundo"


def test_transcribe_audio_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr(transcribe, "WhisperModel", _FakeWhisperModelRaises)
    result = transcribe.transcribe_audio("audio.wav", "small", "cpu", "int8")
    assert result is None
