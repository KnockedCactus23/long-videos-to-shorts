from dataclasses import dataclass
from pathlib import Path

from clipengine.logging_utils import info as log_info
from clipengine.logging_utils import warn

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    segments: list[TranscriptSegment]
    text: str
    language: str | None = None


def transcribe_audio(
    wav_path: Path, model_size: str, device: str, compute_type: str, language: str | None = None
) -> Transcript | None:
    if WhisperModel is None:
        warn("faster-whisper no instalado; pip install -e '.[ai]'. Se omite la transcripción.")
        return None

    try:
        log_info(f"Cargando modelo Whisper '{model_size}' ({device}/{compute_type})...")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        # Si no se fija `language`, Whisper la autodetecta a partir de los primeros ~30s
        # de audio — con directos musicales eso suele ser el intro instrumental/aplausos,
        # sin habla clara, y puede hacer que adivine mal el idioma (ej. inglés por defecto).
        log_info("Transcribiendo audio (puede tardar varios minutos en CPU para directos largos)...")
        segments_iter, transcription_info = model.transcribe(
            str(wav_path), language=language, log_progress=True
        )
        segments = [
            TranscriptSegment(start=s.start, end=s.end, text=s.text.strip())
            for s in segments_iter
        ]
        text = " ".join(s.text for s in segments)
        log_info(f"Transcripción completa: {len(segments)} segmentos.")
        return Transcript(
            segments=segments, text=text, language=getattr(transcription_info, "language", None)
        )
    except Exception as e:
        warn(f"Fallo al transcribir con faster-whisper: {e}. Se omite la transcripción.")
        return None
