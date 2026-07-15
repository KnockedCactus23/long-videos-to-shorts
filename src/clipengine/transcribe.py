from dataclasses import dataclass
from pathlib import Path

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


def transcribe_audio(wav_path: Path, model_size: str, device: str, compute_type: str) -> Transcript | None:
    if WhisperModel is None:
        warn("faster-whisper no instalado; pip install -e '.[ai]'. Se omite la transcripción.")
        return None

    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments_iter, info = model.transcribe(str(wav_path))
        segments = [
            TranscriptSegment(start=s.start, end=s.end, text=s.text.strip())
            for s in segments_iter
        ]
        text = " ".join(s.text for s in segments)
        return Transcript(segments=segments, text=text, language=getattr(info, "language", None))
    except Exception as e:
        warn(f"Fallo al transcribir con faster-whisper: {e}. Se omite la transcripción.")
        return None
