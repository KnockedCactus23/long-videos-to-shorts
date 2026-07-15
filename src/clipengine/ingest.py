from pathlib import Path
from urllib.parse import urlparse

import yt_dlp


def is_url(s: str) -> bool:
    return urlparse(s).scheme in {"http", "https"}


def download_with_ytdlp(url: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info)).with_suffix(".mp4")


def resolve_input(input_str: str, work_dir: Path) -> Path:
    if is_url(input_str):
        return download_with_ytdlp(input_str, work_dir)

    local_path = Path(input_str)
    if not local_path.exists():
        raise FileNotFoundError(f"Archivo de entrada no encontrado: {local_path}")
    return local_path
