import os
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clipengine.config import ClipConfig
from clipengine.logging_utils import info, warn
from clipengine.publish.oauth_server import wait_for_callback
from clipengine.publish.tokens import TokenSet, is_expiring_soon, load_tokens, save_tokens
from clipengine.publish.types import PublishResult

try:
    import requests
except ImportError:
    requests = None

_API_VERSION = "v21.0"
_AUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
_GRAPH_URL = f"https://graph.facebook.com/{_API_VERSION}"
_UPLOAD_URL = "https://rupload.facebook.com/ig-api-upload"
_SCOPE = "instagram_content_publish,instagram_basic,pages_show_list"


def _require_requests() -> None:
    if requests is None:
        raise RuntimeError("requests no instalado; pip install -e '.[publish]'")


def _app_credentials() -> tuple[str, str]:
    app_id = os.getenv("INSTAGRAM_APP_ID")
    app_secret = os.getenv("INSTAGRAM_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("INSTAGRAM_APP_ID/INSTAGRAM_APP_SECRET no configuradas.")
    return app_id, app_secret


def _business_account_id() -> str:
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if not ig_user_id:
        raise RuntimeError("INSTAGRAM_BUSINESS_ACCOUNT_ID no configurada.")
    return ig_user_id


def _raise_for_graph_error(resp) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"Instagram Graph API error {resp.status_code}: {resp.text[:2000]}")


def _save_long_lived_token(data: dict, config: ClipConfig) -> TokenSet:
    # Meta no usa un refresh_token separado para tokens de usuario/página: se
    # "refresca" re-intercambiando el propio access_token (todavía válido) por uno
    # nuevo de 60 días vía el mismo endpoint fb_exchange_token — ver refresh_token().
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 5184000))
    tokens = TokenSet(access_token=data["access_token"], refresh_token=data["access_token"], expires_at=expires_at)
    save_tokens("instagram", tokens, config)
    return tokens


def authorize(config: ClipConfig) -> None:
    """Flujo interactivo (`clipengine auth instagram`): abre el navegador, el usuario
    autoriza la cuenta (debe ser Business/Creator, agregada como Instagram Tester en la
    app), y el token de larga duración resultante queda persistido para las corridas de
    `clipengine publish instagram` posteriores."""
    _require_requests()
    app_id, app_secret = _app_credentials()
    redirect_uri = f"http://localhost:{config.publish_oauth_port}/callback"

    state = secrets.token_urlsafe(24)
    params = urllib.parse.urlencode({
        "client_id": app_id, "redirect_uri": redirect_uri, "scope": _SCOPE,
        "response_type": "code", "state": state,
    })
    info("Abriendo el navegador para autorizar Instagram...")
    result = wait_for_callback(f"{_AUTH_URL}?{params}", config.publish_oauth_port)

    if result.error:
        raise RuntimeError(f"Meta rechazó la autorización: {result.error}")
    if result.state != state:
        raise RuntimeError(
            "El 'state' del callback de Instagram no coincide con el esperado (posible CSRF); abortando."
        )
    if not result.code:
        raise RuntimeError("Meta no devolvió un código de autorización.")

    short_lived = requests.get(f"{_GRAPH_URL}/oauth/access_token", params={
        "client_id": app_id, "client_secret": app_secret,
        "redirect_uri": redirect_uri, "code": result.code,
    })
    _raise_for_graph_error(short_lived)

    long_lived = requests.get(f"{_GRAPH_URL}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": short_lived.json()["access_token"],
    })
    _raise_for_graph_error(long_lived)
    _save_long_lived_token(long_lived.json(), config)
    info("Instagram autorizado correctamente.")


def refresh_token(tokens: TokenSet, config: ClipConfig) -> TokenSet:
    _require_requests()
    app_id, app_secret = _app_credentials()
    resp = requests.get(f"{_GRAPH_URL}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": tokens.access_token,
    })
    if resp.status_code >= 400:
        raise RuntimeError(
            f"El token de Instagram venció y no se pudo refrescar ({resp.status_code}); "
            "correr `clipengine auth instagram` de nuevo."
        )
    return _save_long_lived_token(resp.json(), config)


def _get_valid_token(config: ClipConfig) -> str:
    tokens = load_tokens("instagram", config)
    if tokens is None:
        raise RuntimeError("No hay tokens para Instagram; correr `clipengine auth instagram` primero.")
    if is_expiring_soon(tokens, margin_seconds=3 * 24 * 3600):  # margen de días, no minutos: el token dura 60
        tokens = refresh_token(tokens, config)
    return tokens.access_token


def _create_container(clip_path: Path, caption: str, access_token: str, ig_user_id: str) -> str:
    resp = requests.post(f"{_GRAPH_URL}/{ig_user_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "access_token": access_token,
    })
    _raise_for_graph_error(resp)
    return resp.json()["id"]


def _upload_video(container_id: str, clip_path: Path, access_token: str) -> None:
    video_bytes = clip_path.read_bytes()
    resp = requests.post(
        f"{_UPLOAD_URL}/{_API_VERSION}/{container_id}",
        headers={
            "Authorization": f"OAuth {access_token}",
            "offset": "0", "file_size": str(len(video_bytes)),
        },
        data=video_bytes,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Fallo subiendo el video a Instagram: {resp.status_code} {resp.text[:1000]}")


def _poll_until_finished(container_id: str, access_token: str, config: ClipConfig) -> None:
    deadline = time.monotonic() + config.publish_poll_timeout_seconds
    while time.monotonic() < deadline:
        resp = requests.get(
            f"{_GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
        )
        _raise_for_graph_error(resp)
        status = resp.json()["status_code"]
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram reportó un error procesando el video (container={container_id}).")
        time.sleep(config.publish_poll_interval_seconds)
    raise TimeoutError(
        f"Se agotó el tiempo de espera ({config.publish_poll_timeout_seconds}s) "
        "esperando que Instagram termine de procesar el video."
    )


def _fetch_permalink(media_id: str, access_token: str) -> str | None:
    try:
        resp = requests.get(f"{_GRAPH_URL}/{media_id}", params={"fields": "permalink", "access_token": access_token})
        _raise_for_graph_error(resp)
        return resp.json().get("permalink")
    except Exception as e:  # no crítico: el post ya se publicó, no vale la pena fallar el resultado por esto
        warn(f"No se pudo obtener el permalink del Reel recién publicado: {e}")
        return None


def publish_video(clip_path: Path, clip_id: int, caption: str, config: ClipConfig) -> PublishResult:
    """No atrapa nada — un fallo en cualquier paso se propaga tal cual; el único punto
    que atrapa excepciones es publish/runner.py. A diferencia de TikTok, esto publica de
    inmediato y en público en cuanto media_publish responde — no hay borrador ni forma
    de deshacerlo desde acá."""
    _require_requests()
    if not config.publish_instagram:
        raise RuntimeError("PUBLISH_INSTAGRAM está deshabilitado en la configuración.")

    access_token = _get_valid_token(config)
    ig_user_id = _business_account_id()

    container_id = _create_container(clip_path, caption, access_token, ig_user_id)
    _upload_video(container_id, clip_path, access_token)
    _poll_until_finished(container_id, access_token, config)

    publish_resp = requests.post(f"{_GRAPH_URL}/{ig_user_id}/media_publish", data={
        "creation_id": container_id, "access_token": access_token,
    })
    _raise_for_graph_error(publish_resp)
    media_id = publish_resp.json()["id"]

    info("Publicado en Instagram Reels — visible de inmediato y en público (sin estado de borrador).")
    return PublishResult(
        platform="instagram", clip_id=clip_id, success=True, external_id=media_id,
        permalink=_fetch_permalink(media_id, access_token),
        published_at=datetime.now(timezone.utc).isoformat(),
    )
