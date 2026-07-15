import json
import re

from clipengine.candidates import ClipCandidate, RankedClip
from clipengine.logging_utils import warn
from clipengine.transcribe import Transcript

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

PROMPT_TEMPLATE = """\
Eres un asistente que ayuda a seleccionar los mejores momentos de un directo musical
para clips cortos verticales (TikTok/Reels/Shorts).

Se te da la transcripción completa y una lista de candidatos ya detectados por análisis
de energía de audio (id, start, end en segundos, score).

Elige como máximo {num_clips} candidatos de la lista (usa solo los ids dados, no inventes
timestamps). Para cada uno da: título/hook corto (máx 80 caracteres) y una razón breve
(1 frase). Escribe el título y la razón SIEMPRE EN ESPAÑOL, sin importar el idioma de la
transcripción o de la letra de las canciones (puede haber partes en otros idiomas, pero tu
respuesta debe ser en español). Ordénalos de más a menos interesante.

Responde ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de código, con esta forma:
[{{"candidate_id": 0, "title": "...", "reason": "..."}}, ...]

Transcripción:
\"\"\"{transcript_text}\"\"\"

Candidatos:
{candidates_json}
"""


def build_prompt(transcript: Transcript, candidates: list[ClipCandidate], num_clips: int, max_chars: int) -> str:
    text = transcript.text
    if len(text) > max_chars:
        warn(f"Transcripción truncada de {len(text)} a {max_chars} caracteres para el prompt del LLM.")
        text = text[:max_chars]

    candidates_json = json.dumps(
        [
            {"id": i, "start": round(c.start, 2), "end": round(c.end, 2), "score": round(c.score, 4)}
            for i, c in enumerate(candidates)
        ],
        ensure_ascii=False,
    )

    return PROMPT_TEMPLATE.format(
        num_clips=num_clips, transcript_text=text, candidates_json=candidates_json
    )


def parse_llm_response(raw: str, candidates: list[ClipCandidate]) -> list[RankedClip]:
    cleaned = _FENCE_RE.sub("", raw.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Respuesta del LLM no es JSON válido: {e}") from e

    if not isinstance(data, list):
        raise ValueError("Respuesta del LLM no es una lista JSON.")

    ranked: list[RankedClip] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        candidate_id = item.get("candidate_id")
        title = item.get("title")
        if not isinstance(candidate_id, int) or not isinstance(title, str):
            continue
        if candidate_id < 0 or candidate_id >= len(candidates):
            continue
        reason = item.get("reason")
        ranked.append(
            RankedClip(
                candidate=candidates[candidate_id],
                title=title,
                reason=reason if isinstance(reason, str) else None,
                ai_enhanced=True,
            )
        )

    if not ranked:
        raise ValueError("Ningún item de la respuesta del LLM fue válido.")

    return ranked
