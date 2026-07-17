import json
from dataclasses import asdict
from pathlib import Path

from clipengine.publish.types import PublishResult


def _status_path(output_dir: Path) -> Path:
    return output_dir / "publish_status.json"


def load_status(output_dir: Path) -> dict[tuple[int, str], PublishResult]:
    path = _status_path(output_dir)
    if not path.exists():
        return {}
    records = json.loads(path.read_text())
    return {(r["clip_id"], r["platform"]): PublishResult(**r) for r in records}


def save_status(output_dir: Path, records: dict[tuple[int, str], PublishResult]) -> None:
    """Sobreescribe publish_status.json entero con el estado actual — separado de
    metadata.json a propósito (ver CLAUDE.md Fase 3) para que `clipengine run` sobre el
    mismo output_dir no borre el historial de publicaciones."""
    path = _status_path(output_dir)
    ordered = sorted(records.values(), key=lambda r: (r.clip_id, r.platform))
    path.write_text(json.dumps([asdict(r) for r in ordered], indent=2, ensure_ascii=False))
