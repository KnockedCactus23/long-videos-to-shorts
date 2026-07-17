import argparse
import json
import sys
from pathlib import Path

from clipengine.config import ClipConfig
from clipengine.logging_utils import warn
from clipengine.pipeline import run_pipeline
from clipengine.publish import instagram, runner, tiktok

_AUTH_PLATFORMS = {"tiktok": tiktok, "instagram": instagram}
_PUBLISH_FLAG_ATTR = {"tiktok": "publish_tiktok", "instagram": "publish_instagram"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Recorta y publica clips 9:16 de directos musicales.")
    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Genera los clips a partir de un video/directo.")
    run_p.add_argument("--input", required=True, help="URL o ruta a archivo local")
    run_p.add_argument("--output-dir", default=None)
    run_p.add_argument("--num-clips", type=int, default=None)
    run_p.add_argument("--clip-min-duration", type=float, default=None)
    run_p.add_argument("--clip-max-duration", type=float, default=None)

    pub_p = sub.add_parser("publish", help="Sube clips ya generados por `run` a una plataforma.")
    pub_p.add_argument("platform", choices=["tiktok", "instagram"])
    pub_p.add_argument("--output-dir", required=True)
    pub_p.add_argument("--clips", default=None, help="Ej: 1,3,5 (numeración 1-indexada, la de los archivos)")
    pub_p.add_argument("--force", action="store_true", help="Republica aunque ya haya un intento exitoso registrado")
    pub_p.add_argument("--dry-run", action="store_true", help="Muestra qué se publicaría, sin llamar a la API real")

    auth_p = sub.add_parser("auth", help="Autoriza una plataforma la primera vez (abre el navegador).")
    auth_p.add_argument("platform", choices=["tiktok", "instagram"])

    return p


def _run(args: argparse.Namespace) -> None:
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


def _parse_clip_selection(raw: str | None) -> set[int] | None:
    """--clips usa la numeración 1-indexada que ve el usuario en los archivos
    (clip_01.mp4, ...); metadata.json usa "id" 0-indexado — acá se convierte una única
    vez, en el único lugar de la CLI que necesita saber que existe esa diferencia."""
    if raw is None:
        return None
    return {int(n.strip()) - 1 for n in raw.split(",") if n.strip()}


def _publish(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    metadata_path = output_dir / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit(f"No se encontró {metadata_path} — corré `clipengine run` primero.")

    config = ClipConfig()
    flag_attr = _PUBLISH_FLAG_ATTR[args.platform]
    if not getattr(config, flag_attr) and not args.dry_run:
        raise SystemExit(
            f"PUBLISH_{args.platform.upper()} está deshabilitado en la configuración; "
            "activalo en .env o usá --dry-run para solo previsualizar."
        )

    metadata = json.loads(metadata_path.read_text())
    clips = metadata["clips"]

    selected_ids = _parse_clip_selection(args.clips)
    if selected_ids is not None:
        clips = [c for c in clips if c["id"] in selected_ids]

    results = runner.publish_clips(
        clips, output_dir, args.platform, config, force=args.force, dry_run=args.dry_run
    )

    if args.dry_run:
        return

    failed = [r for r in results if not r.success]
    print(f"Publicados {len(results) - len(failed)}/{len(results)} clips en {args.platform}.")
    if failed:
        for r in failed:
            warn(f"Clip {r.clip_id}: {r.error}")
        sys.exit(1)


def _auth(args: argparse.Namespace) -> None:
    config = ClipConfig()
    _AUTH_PLATFORMS[args.platform].authorize(config)


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        _run(args)
    elif args.command == "publish":
        _publish(args)
    elif args.command == "auth":
        _auth(args)


if __name__ == "__main__":
    main()
