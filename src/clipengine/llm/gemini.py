import os

from clipengine.candidates import ClipCandidate, RankedClip
from clipengine.config import ClipConfig
from clipengine.llm.prompt import build_prompt, parse_llm_response
from clipengine.transcribe import Transcript

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


def rank_and_title(transcript: Transcript, candidates: list[ClipCandidate], config: ClipConfig) -> list[RankedClip]:
    if genai is None:
        raise RuntimeError("google-genai no instalado; pip install -e '.[ai]'")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no configurada")

    http_options = types.HttpOptions(timeout=int(config.llm_timeout_seconds * 1000))
    client = genai.Client(api_key=api_key, http_options=http_options)
    prompt = build_prompt(transcript, candidates, config.num_clips, config.max_transcript_chars)
    response = client.models.generate_content(model=config.gemini_model, contents=prompt)
    return parse_llm_response(response.text, candidates)
