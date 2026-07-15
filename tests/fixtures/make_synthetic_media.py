"""Genera un video sintético (sin red) con ráfagas de ruido blanco cada 10s,
simulando aplausos/vítores intercalados con un tono suave de fondo."""

import subprocess
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "synthetic_concert.mp4"


def make_synthetic_media(output_path: Path = OUTPUT_PATH, duration: int = 180) -> Path:
    audio_expr = (
        "if(mod(floor(t/10),2),0.9*random(0),0.05*sin(2*PI*220*t))"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=gray:s=1280x720:d={duration}:r=25",
        "-f", "lavfi", "-i", f"aevalsrc=exprs='{audio_expr}':s=16000:d={duration}",
        "-shortest",
        "-loglevel", "error",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return output_path


if __name__ == "__main__":
    path = make_synthetic_media()
    print(f"Fixture generada en: {path}")
