import base64
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clipengine.config import ClipConfig
from clipengine.logging_utils import info
from clipengine.publish.oauth_server import wait_for_callback
from clipengine.publish.tokens import TokenSet, is_expiring_soon, load_tokens, save_tokens
from clipengine.publish.types import PublishResult

try:
    import requests
except ImportError:
    requests = None

_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

_SCOPE = "video.publish"
_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB — dentro del rango 5-64MB que exige la API


def _require_requests() -> None:
    if requests is None:
        raise RuntimeError("requests no instalado; pip install -e '.[publish]'")


def _app_credentials() -> tuple[str, str]:
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
    if not client_key or not client_secret:
        raise RuntimeError("TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET no configuradas.")
    return client_key, client_secret


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _raise_for_tiktok_error(resp) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"TikTok API error {resp.status_code}: {resp.text[:2000]}")
    data = resp.json()
    error = data.get("error")
    if isinstance(error, dict) and error.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok API error: {error}")


def _save_token_response(data: dict, config: ClipConfig) -> TokenSet:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
    tokens = TokenSet(
        access_token=data["access_token"], refresh_token=data.get("refresh_token"),
        expires_at=expires_at, extra={"open_id": data.get("open_id")},
    )
    save_tokens("tiktok", tokens, config)
    return tokens


def authorize(config: ClipConfig) -> None:
    """Flujo interactivo (`clipengine auth tiktok`): abre el navegador, el usuario
    autoriza la cuenta, y el token resultante queda persistido para las corridas de
    `clipengine publish tiktok` posteriores."""
    _require_requests()
    client_key, client_secret = _app_credentials()
    redirect_uri = f"http://localhost:{config.publish_oauth_port}/callback"

    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()

    auth_url = (
        f"{_AUTH_URL}?client_key={client_key}&response_type=code&scope={_SCOPE}"
        f"&redirect_uri={redirect_uri}&state={state}"
        f"&code_challenge={challenge}&code_challenge_method=S256"
    )
    info("Abriendo el navegador para autorizar TikTok...")
    result = wait_for_callback(auth_url, config.publish_oauth_port)

    if result.error:
        raise RuntimeError(f"TikTok rechazó la autorización: {result.error}")
    if result.state != state:
        raise RuntimeError("El 'state' del callback de TikTok no coincide con el esperado (posible CSRF); abortando.")
    if not result.code:
        raise RuntimeError("TikTok no devolvió un código de autorización.")

    resp = requests.post(_TOKEN_URL, data={
        "client_key": client_key, "client_secret": client_secret, "code": result.code,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri, "code_verifier": verifier,
    })
    _raise_for_tiktok_error(resp)
    _save_token_response(resp.json(), config)
    info("TikTok autorizado correctamente.")


def refresh_token(tokens: TokenSet, config: ClipConfig) -> TokenSet:
    _require_requests()
    client_key, client_secret = _app_credentials()
    if not tokens.refresh_token:
        raise RuntimeError("No hay refresh_token guardado para TikTok; correr `clipengine auth tiktok` de nuevo.")
    resp = requests.post(_TOKEN_URL, data={
        "client_key": client_key, "client_secret": client_secret,
        "grant_type": "refresh_token", "refresh_token": tokens.refresh_token,
    })
    if resp.status_code >= 400:
        raise RuntimeError(
            f"El token de TikTok venció y no se pudo refrescar ({resp.status_code}); "
            "correr `clipengine auth tiktok` de nuevo."
        )
    return _save_token_response(resp.json(), config)


def _get_valid_token(config: ClipConfig) -> str:
    tokens = load_tokens("tiktok", config)
    if tokens is None:
        raise RuntimeError("No hay tokens para TikTok; correr `clipengine auth tiktok` primero.")
    if is_expiring_soon(tokens):
        tokens = refresh_token(tokens, config)
    return tokens.access_token


def _upload_chunks(upload_url: str, clip_path: Path, video_size: int, chunk_size: int, total_chunks: int) -> None:
    with open(clip_path, "rb") as f:
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, video_size) - 1
            f.seek(start)
            data = f.read(end - start + 1)
            resp = requests.put(
                upload_url, data=data,
                headers={"Content-Range": f"bytes {start}-{end}/{video_size}", "Content-Type": "video/mp4"},
            )
            if resp.status_code not in (200, 201, 206):
                raise RuntimeError(
                    f"Fallo subiendo chunk {i + 1}/{total_chunks} a TikTok: {resp.status_code} {resp.text[:1000]}"
                )


def _poll_until_published(publish_id: str, access_token: str, config: ClipConfig) -> None:
    deadline = time.monotonic() + config.publish_poll_timeout_seconds
    while time.monotonic() < deadline:
        resp = requests.post(
            _STATUS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"publish_id": publish_id},
        )
        _raise_for_tiktok_error(resp)
        status = resp.json()["data"]["status"]
        if status == "PUBLISH_COMPLETE":
            return
        if status == "FAILED":
            raise RuntimeError(f"TikTok reportó un fallo al procesar la publicación (publish_id={publish_id}).")
        time.sleep(config.publish_poll_interval_seconds)
    raise TimeoutError(
        f"Se agotó el tiempo de espera ({config.publish_poll_timeout_seconds}s) "
        "esperando que TikTok termine de procesar el video."
    )


def publish_video(clip_path: Path, clip_id: int, caption: str, config: ClipConfig) -> PublishResult:
    """No atrapa nada — un fallo en cualquier paso se propaga tal cual; el único punto
    que atrapa excepciones es publish/runner.py, igual que gemini.py con llm/dispatcher.py."""
    _require_requests()
    if not config.publish_tiktok:
        raise RuntimeError("PUBLISH_TIKTOK está deshabilitado en la configuración.")

    access_token = _get_valid_token(config)
    video_size = clip_path.stat().st_size
    chunk_size = min(_CHUNK_SIZE, video_size) or video_size
    total_chunks = max(1, -(-video_size // chunk_size))  # ceil div

    init_resp = requests.post(
        _INIT_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "post_info": {"title": caption[:150], "privacy_level": "SELF_ONLY"},
            "source_info": {
                "source": "FILE_UPLOAD", "video_size": video_size,
                "chunk_size": chunk_size, "total_chunk_count": total_chunks,
            },
        },
    )
    _raise_for_tiktok_error(init_resp)
    init_data = init_resp.json()["data"]
    publish_id = init_data["publish_id"]
    upload_url = init_data["upload_url"]

    _upload_chunks(upload_url, clip_path, video_size, chunk_size, total_chunks)
    _poll_until_published(publish_id, access_token, config)

    info(
        "Publicado en TikTok como privado (SELF_ONLY) — la app todavía no está "
        "auditada; cambiá la visibilidad a mano en la app de TikTok si lo querés público."
    )
    return PublishResult(
        platform="tiktok", clip_id=clip_id, success=True, external_id=publish_id,
        published_at=datetime.now(timezone.utc).isoformat(),
    )
