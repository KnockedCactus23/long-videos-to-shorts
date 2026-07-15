from pathlib import Path

from clipengine.transcribe import Transcript, TranscriptSegment


def slice_transcript(transcript: Transcript, start: float, end: float) -> list[TranscriptSegment]:
    sliced = []
    for seg in transcript.segments:
        if seg.end <= start or seg.start >= end:
            continue
        sliced.append(
            TranscriptSegment(
                start=max(seg.start, start) - start,
                end=min(seg.end, end) - start,
                text=seg.text,
            )
        )
    return sliced


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, millis = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(segments: list[TranscriptSegment], out_path: Path) -> Path | None:
    if not segments:
        return None

    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_format_srt_timestamp(seg.start)} --> {_format_srt_timestamp(seg.end)}")
        lines.append(seg.text)
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
