from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClipCandidate:
    start: float
    end: float
    peak_time: float
    score: float
    source: str = "audio_energy"


@dataclass
class RankedClip:
    candidate: ClipCandidate
    title: str
    reason: str | None = None
    ai_enhanced: bool = False
    subtitles_path: Path | None = None


def build_candidates(
    peaks: list[tuple[float, float]],
    target_duration: float,
    min_duration: float,
    max_duration: float,
    total_duration: float,
) -> list[ClipCandidate]:
    out = []
    for peak_time, score in peaks:
        start = max(0.0, peak_time - target_duration / 2)
        end = min(total_duration, start + target_duration)
        start = max(0.0, end - target_duration)  # re-clamp si tocó el borde final
        end = min(end, start + max_duration)
        if end - start >= min_duration:
            out.append(ClipCandidate(start=start, end=end, peak_time=peak_time, score=score))
    return out


def select_top_n(candidates: list[ClipCandidate], n: int, min_gap: float) -> list[ClipCandidate]:
    """NMS greedy: ordena por score desc, acepta si no solapa (con margen min_gap)
    con los ya elegidos."""
    chosen: list[ClipCandidate] = []
    for c in sorted(candidates, key=lambda c: c.score, reverse=True):
        if all(c.end + min_gap <= o.start or o.end + min_gap <= c.start for o in chosen):
            chosen.append(c)
        if len(chosen) == n:
            break
    return sorted(chosen, key=lambda c: c.start)
