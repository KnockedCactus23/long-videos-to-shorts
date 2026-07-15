from pathlib import Path

from clipengine.candidates import ClipCandidate
from clipengine.proc import run


def render_clip(
    source_path: Path,
    candidate: ClipCandidate,
    out_path: Path,
    width: int,
    height: int,
    crf: int,
    subtitle_path: Path | None = None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = candidate.end - candidate.start
    # crop sin x/y explícitos: ffmpeg centra automáticamente el recorte.
    vf_parts = ["crop=ih*9/16:ih", f"scale={width}:{height}:flags=lanczos", "setsar=1"]
    if subtitle_path is not None:
        escaped = str(subtitle_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf_parts.append(f"subtitles='{escaped}'")
    vf = ",".join(vf_parts)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{candidate.start:.3f}", "-i", str(source_path),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    run(cmd)
