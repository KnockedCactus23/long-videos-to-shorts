from clipengine.candidates import ClipCandidate, RankedClip
from clipengine.config import ClipConfig
from clipengine.llm import gemini
from clipengine.logging_utils import warn
from clipengine.transcribe import Transcript

_PROVIDERS = {
    "gemini": gemini.rank_and_title,
}


def rank_and_title(transcript: Transcript, candidates: list[ClipCandidate], config: ClipConfig) -> list[RankedClip] | None:
    fn = _PROVIDERS.get((config.llm_provider or "").lower())
    if fn is None:
        warn(f"LLM_PROVIDER '{config.llm_provider}' no soportado; se usa señal pura.")
        return None
    try:
        return fn(transcript, candidates, config)
    except Exception as e:
        warn(f"Fallo en la capa de IA ({config.llm_provider}): {e}. Se usa señal pura.")
        return None
