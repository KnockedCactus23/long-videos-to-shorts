import json

import pytest

from clipengine.candidates import ClipCandidate
from clipengine.config import ClipConfig
from clipengine.llm import dispatcher, gemini
from clipengine.llm.prompt import build_prompt, parse_llm_response
from clipengine.transcribe import Transcript, TranscriptSegment


def _candidates():
    return [
        ClipCandidate(start=0, end=10, peak_time=5, score=0.5),
        ClipCandidate(start=20, end=30, peak_time=25, score=0.8),
    ]


# ---------- parse_llm_response ----------

def test_parse_llm_response_valid_json():
    raw = json.dumps([{"candidate_id": 1, "title": "Muy bueno", "reason": "sube la energía"}])
    ranked = parse_llm_response(raw, _candidates())
    assert len(ranked) == 1
    assert ranked[0].title == "Muy bueno"
    assert ranked[0].reason == "sube la energía"
    assert ranked[0].ai_enhanced is True
    assert ranked[0].candidate.start == 20


def test_parse_llm_response_strips_code_fences():
    raw = "```json\n" + json.dumps([{"candidate_id": 0, "title": "X"}]) + "\n```"
    ranked = parse_llm_response(raw, _candidates())
    assert len(ranked) == 1


def test_parse_llm_response_invalid_json_raises():
    with pytest.raises(ValueError):
        parse_llm_response("esto no es json", _candidates())


def test_parse_llm_response_discards_out_of_range_id():
    raw = json.dumps([
        {"candidate_id": 0, "title": "Válido"},
        {"candidate_id": 99, "title": "Fuera de rango"},
    ])
    ranked = parse_llm_response(raw, _candidates())
    assert len(ranked) == 1
    assert ranked[0].title == "Válido"


def test_parse_llm_response_empty_after_filtering_raises():
    raw = json.dumps([{"candidate_id": 99, "title": "Fuera de rango"}])
    with pytest.raises(ValueError):
        parse_llm_response(raw, _candidates())


def test_build_prompt_truncates_long_transcript():
    transcript = Transcript(segments=[], text="a" * 100)
    prompt_text = build_prompt(transcript, _candidates(), num_clips=2, max_chars=10)
    assert "a" * 100 not in prompt_text
    assert "a" * 10 in prompt_text


# ---------- gemini.rank_and_title (mockeado) ----------

class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, response_text):
        self._response_text = response_text

    def generate_content(self, model, contents):
        return _FakeResponse(self._response_text)


class _FakeClient:
    def __init__(self, response_text, **kwargs):
        self.models = _FakeModels(response_text)


class _FakeHttpOptions:
    def __init__(self, timeout=None):
        self.timeout = timeout


def _make_fake_genai(response_text):
    class FakeGenAIModule:
        @staticmethod
        def Client(**kwargs):
            return _FakeClient(response_text)

    return FakeGenAIModule()


class _FakeTypesModule:
    HttpOptions = _FakeHttpOptions


def test_gemini_rank_and_title_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    response_text = json.dumps([{"candidate_id": 0, "title": "Gran momento", "reason": "porque sí"}])
    monkeypatch.setattr(gemini, "genai", _make_fake_genai(response_text))
    monkeypatch.setattr(gemini, "types", _FakeTypesModule())

    transcript = Transcript(segments=[], text="hola mundo")
    config = ClipConfig(num_clips=1)
    ranked = gemini.rank_and_title(transcript, _candidates(), config)

    assert ranked[0].title == "Gran momento"
    assert ranked[0].ai_enhanced is True


def test_gemini_rank_and_title_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(gemini, "genai", _make_fake_genai("[]"))
    monkeypatch.setattr(gemini, "types", _FakeTypesModule())

    transcript = Transcript(segments=[], text="hola")
    config = ClipConfig()
    with pytest.raises(RuntimeError):
        gemini.rank_and_title(transcript, _candidates(), config)


def test_gemini_rank_and_title_not_installed(monkeypatch):
    monkeypatch.setattr(gemini, "genai", None)
    transcript = Transcript(segments=[], text="hola")
    config = ClipConfig()
    with pytest.raises(RuntimeError):
        gemini.rank_and_title(transcript, _candidates(), config)


# ---------- dispatcher.rank_and_title (nunca lanza) ----------

def test_dispatcher_returns_none_for_unsupported_provider():
    config = ClipConfig(llm_provider="inexistente")
    transcript = Transcript(segments=[], text="hola")
    result = dispatcher.rank_and_title(transcript, _candidates(), config)
    assert result is None


def test_dispatcher_returns_none_when_provider_raises(monkeypatch):
    def _boom(transcript, candidates, config):
        raise RuntimeError("fallo simulado")

    monkeypatch.setitem(dispatcher._PROVIDERS, "gemini", _boom)
    config = ClipConfig(llm_provider="gemini")
    transcript = Transcript(segments=[], text="hola")
    result = dispatcher.rank_and_title(transcript, _candidates(), config)
    assert result is None
