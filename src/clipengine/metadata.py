import json
from datetime import datetime, timezone
from pathlib import Path

from clipengine.candidates import RankedClip


def build_metadata(ranked: list[RankedClip], source_info: dict, clip_paths: list[Path]) -> dict:
    return {
        "source": source_info,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_enhanced": any(r.ai_enhanced for r in ranked),
        "clips": [
            {
                "id": i,
                "file": path.name,
                "start": round(r.candidate.start, 2),
                "end": round(r.candidate.end, 2),
                "duration": round(r.candidate.end - r.candidate.start, 2),
                "score": round(r.candidate.score, 4),
                "title": r.title,
                "reason": r.reason,
                "signal_source": r.candidate.source,
                "ai_enhanced": r.ai_enhanced,
                "has_subtitles": r.subtitles_path is not None,
            }
            for i, (r, path) in enumerate(zip(ranked, clip_paths))
        ],
    }


def write_metadata(metadata: dict, out_path: Path) -> None:
    out_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
