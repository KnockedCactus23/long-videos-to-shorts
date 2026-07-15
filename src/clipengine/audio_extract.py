import json
from pathlib import Path

from clipengine.proc import run


def extract_audio(source_path: Path, out_wav_path: Path, sample_rate: int = 16000) -> Path:
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source_path),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-acodec", "pcm_s16le",
        str(out_wav_path),
    ]
    run(cmd)
    return out_wav_path


def probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    out = run(cmd, text=True)
    return float(json.loads(out.stdout)["format"]["duration"])
