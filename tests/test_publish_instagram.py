from datetime import datetime, timedelta, timezone

import pytest

from clipengine.config import ClipConfig
from clipengine.publish import instagram
from clipengine.publish.oauth_server import OAuthCallbackResult
from clipengine.publish.tokens import TokenSet, load_tokens, save_tokens


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json_data


class _FakeRequests:
    """Igual criterio que en test_publish_tiktok.py: con una sola respuesta configurada
    para una URL, la repite en llamadas sucesivas; con varias, las consume en orden —
    así una misma URL llamada dos veces con distinto propósito (ej. oauth/access_token
    para el intercambio corto y luego el de larga duración) puede devolver respuestas
    distintas en cada llamada."""

    def __init__(self, responses: dict):
        self._responses = {url: list(seq) for url, seq in responses.items()}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._next(url)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._next(url)

    def _next(self, url):
        queue = self._responses[url]
        return queue.pop(0) if len(queue) > 1 else queue[0]


_IG_USER_ID = "IGUSER1"
_CONTAINER_ID = "CONTAINER1"
_MEDIA_ID = "MEDIA1"
_OAUTH_URL = f"{instagram._GRAPH_URL}/oauth/access_token"
_MEDIA_CREATE_URL = f"{instagram._GRAPH_URL}/{_IG_USER_ID}/media"
_UPLOAD_URL = f"{instagram._UPLOAD_URL}/{instagram._API_VERSION}/{_CONTAINER_ID}"
_STATUS_URL = f"{instagram._GRAPH_URL}/{_CONTAINER_ID}"
_PUBLISH_URL = f"{instagram._GRAPH_URL}/{_IG_USER_ID}/media_publish"
_PERMALINK_URL = f"{instagram._GRAPH_URL}/{_MEDIA_ID}"


def _config(tmp_path, **overrides):
    defaults = dict(
        work_dir=tmp_path / "work", output_dir=tmp_path / "output",
        publish_token_dir=tmp_path / "tokens", publish_instagram=True,
        publish_poll_interval_seconds=0.01, publish_poll_timeout_seconds=1,
    )
    defaults.update(overrides)
    return ClipConfig(**defaults)


def _clip(tmp_path, size=1024):
    path = tmp_path / "clip_01.mp4"
    path.write_bytes(b"x" * size)
    return path


def _valid_tokens():
    return TokenSet(
        access_token="tok", refresh_token="tok",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )


def _happy_path_responses(container_status_sequence=("FINISHED",), with_permalink=True):
    responses = {
        _MEDIA_CREATE_URL: [_FakeResponse(200, {"id": _CONTAINER_ID})],
        _UPLOAD_URL: [_FakeResponse(200)],
        _STATUS_URL: [_FakeResponse(200, {"status_code": s}) for s in container_status_sequence],
        _PUBLISH_URL: [_FakeResponse(200, {"id": _MEDIA_ID})],
    }
    if with_permalink:
        responses[_PERMALINK_URL] = [_FakeResponse(200, {"permalink": "https://instagram.com/reel/xyz"})]
    else:
        responses[_PERMALINK_URL] = [_FakeResponse(500, text="temporarily unavailable")]
    return responses


# ---------- publish_video ----------

def test_publish_video_disabled_flag_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(instagram, "requests", _FakeRequests({}))
    config = _config(tmp_path, publish_instagram=False)
    with pytest.raises(RuntimeError, match="PUBLISH_INSTAGRAM"):
        instagram.publish_video(_clip(tmp_path), 0, "titulo", config)


def test_publish_video_requires_prior_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(instagram, "requests", _FakeRequests({}))
    config = _config(tmp_path)
    with pytest.raises(RuntimeError, match="clipengine auth instagram"):
        instagram.publish_video(_clip(tmp_path), 0, "titulo", config)


def test_publish_video_success_after_polling(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", _IG_USER_ID)
    save_tokens("instagram", _valid_tokens(), config)

    fake = _FakeRequests(_happy_path_responses(container_status_sequence=("IN_PROGRESS", "FINISHED")))
    monkeypatch.setattr(instagram, "requests", fake)

    result = instagram.publish_video(_clip(tmp_path), 2, "un título", config)

    assert result.success is True
    assert result.platform == "instagram"
    assert result.clip_id == 2
    assert result.external_id == _MEDIA_ID
    assert result.permalink == "https://instagram.com/reel/xyz"


def test_publish_video_permalink_failure_does_not_fail_the_result(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", _IG_USER_ID)
    save_tokens("instagram", _valid_tokens(), config)

    fake = _FakeRequests(_happy_path_responses(with_permalink=False))
    monkeypatch.setattr(instagram, "requests", fake)

    result = instagram.publish_video(_clip(tmp_path), 0, "t", config)

    assert result.success is True  # el Reel ya se publicó; el permalink es solo un extra
    assert result.permalink is None


def test_publish_video_upload_failure_raises(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", _IG_USER_ID)
    save_tokens("instagram", _valid_tokens(), config)

    responses = _happy_path_responses()
    responses[_UPLOAD_URL] = [_FakeResponse(500, text="server error")]
    fake = _FakeRequests(responses)
    monkeypatch.setattr(instagram, "requests", fake)

    with pytest.raises(RuntimeError, match="subiendo"):
        instagram.publish_video(_clip(tmp_path), 0, "t", config)


def test_publish_video_polling_timeout_raises(tmp_path, monkeypatch):
    config = _config(tmp_path, publish_poll_timeout_seconds=0.05, publish_poll_interval_seconds=0.01)
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", _IG_USER_ID)
    save_tokens("instagram", _valid_tokens(), config)

    fake = _FakeRequests(_happy_path_responses(container_status_sequence=("IN_PROGRESS",)))
    monkeypatch.setattr(instagram, "requests", fake)

    with pytest.raises(TimeoutError):
        instagram.publish_video(_clip(tmp_path), 0, "t", config)


def test_publish_video_platform_reported_error_raises(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", _IG_USER_ID)
    save_tokens("instagram", _valid_tokens(), config)

    fake = _FakeRequests(_happy_path_responses(container_status_sequence=("ERROR",)))
    monkeypatch.setattr(instagram, "requests", fake)

    with pytest.raises(RuntimeError, match="error"):
        instagram.publish_video(_clip(tmp_path), 0, "t", config)


def test_requests_not_installed_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(instagram, "requests", None)
    config = _config(tmp_path)
    with pytest.raises(RuntimeError, match="pip install"):
        instagram.publish_video(_clip(tmp_path), 0, "t", config)


# ---------- refresh de tokens ----------

def test_publish_video_refreshes_expiring_token(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_APP_ID", "app")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "secret")
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", _IG_USER_ID)
    expiring = TokenSet(
        access_token="old", refresh_token="old",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),  # dentro del margen de días
    )
    save_tokens("instagram", expiring, config)

    responses = _happy_path_responses()
    responses[_OAUTH_URL] = [_FakeResponse(200, {"access_token": "new", "expires_in": 5184000})]
    fake = _FakeRequests(responses)
    monkeypatch.setattr(instagram, "requests", fake)

    result = instagram.publish_video(_clip(tmp_path), 0, "t", config)

    assert result.success is True
    reloaded = load_tokens("instagram", config)
    assert reloaded.access_token == "new"
    create_call = next(c for c in fake.calls if c[1] == _MEDIA_CREATE_URL)
    assert create_call[2]["data"]["access_token"] == "new"


def test_refresh_token_http_error_raises_actionable_message(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_APP_ID", "app")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "secret")
    fake = _FakeRequests({_OAUTH_URL: [_FakeResponse(401, text="invalid token")]})
    monkeypatch.setattr(instagram, "requests", fake)
    tokens = TokenSet(access_token="tok", refresh_token="tok", expires_at=datetime.now(timezone.utc))
    with pytest.raises(RuntimeError, match="auth instagram"):
        instagram.refresh_token(tokens, config)


# ---------- authorize(): protección CSRF ----------

def test_authorize_rejects_state_mismatch(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_APP_ID", "app")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "secret")
    monkeypatch.setattr(instagram, "requests", _FakeRequests({}))
    monkeypatch.setattr(
        instagram, "wait_for_callback",
        lambda auth_url, port: OAuthCallbackResult(code="abc", state="state-que-no-coincide", error=None),
    )

    with pytest.raises(RuntimeError, match="state"):
        instagram.authorize(config)


def test_authorize_raises_on_platform_error(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("INSTAGRAM_APP_ID", "app")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", "secret")
    monkeypatch.setattr(instagram, "requests", _FakeRequests({}))
    monkeypatch.setattr(
        instagram, "wait_for_callback",
        lambda auth_url, port: OAuthCallbackResult(code=None, state=None, error="access_denied"),
    )

    with pytest.raises(RuntimeError, match="access_denied"):
        instagram.authorize(config)
