import argparse
from pathlib import Path

from clipengine.config import ClipConfig
from clipengine.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Recorta clips 9:16 de directos musicales.")
    p.add_argument("--input", required=True, help="URL o ruta a archivo local")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--num-clips", type=int, default=None)
    p.add_argument("--clip-min-duration", type=float, default=None)
    p.add_argument("--clip-max-duration", type=float, default=None)
    return p


def main() -> None:
    args = build_parser().parse_args()
    config = ClipConfig()
    if args.output_dir:
        config.output_dir = Path(args.output_dir)
    if args.num_clips:
        config.num_clips = args.num_clips
    if args.clip_min_duration:
        config.clip_min_duration = args.clip_min_duration
    if args.clip_max_duration:
        config.clip_max_duration = args.clip_max_duration

    out = run_pipeline(args.input, config)
    print(f"Clips generados en: {out}")


if __name__ == "__main__":
    main()
