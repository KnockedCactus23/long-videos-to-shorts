from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import download_range_func


def is_url(s: str) -> bool:
    return urlparse(s).scheme in {"http", "https"}


def resolve_local_input(input_str: str) -> Path:
    local_path = Path(input_str)
    if not local_path.exists():
        raise FileNotFoundError(f"Archivo de entrada no encontrado: {local_path}")
    return local_path


def download_audio_only(url: str, dest_dir: Path) -> Path:
    """Descarga solo el audio del directo (mucho más liviano que el video completo:
    unos pocos MB por hora en vez de varios GB). Es todo lo que necesita el análisis
    de señal y la transcripción — nunca se baja el video en esta etapa."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "source_audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info))


def download_video_segment(url: str, start: float, end: float, dest_path: Path) -> Path:
    """Descarga solo el rango [start, end] (en segundos) de video+audio del directo,
    usando la opción de rangos de yt-dlp (equivalente a --download-sections) para no
    tener que traer el archivo completo. Se llama una vez por cada clip ya
    seleccionado, después de que el análisis de audio determinó los timestamps."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_path),
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)
    return dest_path
