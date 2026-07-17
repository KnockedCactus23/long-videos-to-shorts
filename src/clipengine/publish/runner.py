from pathlib import Path

from clipengine.config import ClipConfig
from clipengine.logging_utils import info, warn
from clipengine.publish import instagram, tiktok
from clipengine.publish.status import load_status, save_status
from clipengine.publish.types import PublishResult

_TARGETS = {"tiktok": tiktok.publish_video, "instagram": instagram.publish_video}


def _caption_for(clip: dict) -> str:
    if clip.get("reason"):
        return f"{clip['title']} — {clip['reason']}"
    return clip["title"]


def publish_clips(
    clips: list[dict], output_dir: Path, platform: str, config: ClipConfig,
    force: bool = False, dry_run: bool = False,
) -> list[PublishResult]:
    """Publica en UNA sola plataforma (la elegida explícitamente por el usuario en la
    invocación de `clipengine publish <plataforma>`), iterando los clips ya generados en
    output_dir (`clips` viene de metadata.json["clips"]). Nunca lanza — un fallo en un
    clip se atrapa acá, se acumula como PublishResult(success=False) y se sigue con el
    siguiente, igual que un clip fallido no aborta el resto de la corrida en
    pipeline.py. `tiktok.py`/`instagram.py` en cambio no atrapan nada — este es el único
    punto que lo hace."""
    if platform not in _TARGETS:
        raise ValueError(f"Plataforma desconocida: {platform!r}")

    publish_fn = _TARGETS[platform]
    status = load_status(output_dir)
    results: list[PublishResult] = []

    for clip in clips:
        clip_id = clip["id"]
        key = (clip_id, platform)
        previous = status.get(key)
        if previous is not None and previous.success and not force:
            warn(
                f"Clip {clip_id} ya publicado en {platform} ({previous.external_id}); "
                "se omite (usar --force para republicar)."
            )
            results.append(previous)
            continue

        clip_path = output_dir / clip["file"]
        caption = _caption_for(clip)

        if dry_run:
            info(f"[dry-run] Se publicaría el clip {clip_id} en {platform}: {clip_path.name} (caption: {caption!r})")
            continue

        info(f"Publicando clip {clip_id} en {platform}: {clip_path.name}...")
        try:
            result = publish_fn(clip_path, clip_id, caption, config)
        except Exception as e:
            warn(f"Fallo al publicar el clip {clip_id} en {platform}: {e}")
            result = PublishResult(platform=platform, clip_id=clip_id, success=False, error=str(e))

        status[key] = result
        results.append(result)

    if not dry_run:
        save_status(output_dir, status)
    return results
