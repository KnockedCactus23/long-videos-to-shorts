from datetime import datetime, timedelta, timezone

import pytest

from clipengine.config import ClipConfig
from clipengine.publish import tiktok
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
    """Responde según la URL pedida; con una sola respuesta configurada para una URL,
    la repite en llamadas sucesivas (útil para simular polling que nunca cambia de
    estado, ej. el caso de timeout)."""

    def __init__(self, responses: dict):
        self._responses = {url: list(seq) for url, seq in responses.items()}
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._next(url)

    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return self._next(url)

    def _next(self, url):
        queue = self._responses[url]
        return queue.pop(0) if len(queue) > 1 else queue[0]


def _config(tmp_path, **overrides):
    defaults = dict(
        work_dir=tmp_path / "work", output_dir=tmp_path / "output",
        publish_token_dir=tmp_path / "tokens", publish_tiktok=True,
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
        access_token="tok", refresh_token="ref",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


_UPLOAD_URL = "https://upload.example/x"


def _init_response(publish_id="pid1"):
    return _FakeResponse(200, {"data": {"publish_id": publish_id, "upload_url": _UPLOAD_URL}})


# ---------- publish_video ----------

def test_publish_video_disabled_flag_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(tiktok, "requests", _FakeRequests({}))
    config = _config(tmp_path, publish_tiktok=False)
    with pytest.raises(RuntimeError, match="PUBLISH_TIKTOK"):
        tiktok.publish_video(_clip(tmp_path), 0, "titulo", config)


def test_publish_video_requires_prior_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(tiktok, "requests", _FakeRequests({}))
    config = _config(tmp_path)
    with pytest.raises(RuntimeError, match="clipengine auth tiktok"):
        tiktok.publish_video(_clip(tmp_path), 0, "titulo", config)


def test_publish_video_success_after_polling(tmp_path, monkeypatch):
    config = _config(tmp_path)
    save_tokens("tiktok", _valid_tokens(), config)

    fake = _FakeRequests({
        tiktok._INIT_URL: [_init_response()],
        _UPLOAD_URL: [_FakeResponse(200)],
        tiktok._STATUS_URL: [
            _FakeResponse(200, {"data": {"status": "PROCESSING_UPLOAD"}}),
            _FakeResponse(200, {"data": {"status": "PUBLISH_COMPLETE"}}),
        ],
    })
    monkeypatch.setattr(tiktok, "requests", fake)

    result = tiktok.publish_video(_clip(tmp_path), 3, "un título", config)

    assert result.success is True
    assert result.platform == "tiktok"
    assert result.clip_id == 3
    assert result.external_id == "pid1"


def test_publish_video_upload_chunk_failure_raises(tmp_path, monkeypatch):
    config = _config(tmp_path)
    save_tokens("tiktok", _valid_tokens(), config)
    fake = _FakeRequests({
        tiktok._INIT_URL: [_init_response()],
        _UPLOAD_URL: [_FakeResponse(500, text="server error")],
    })
    monkeypatch.setattr(tiktok, "requests", fake)

    with pytest.raises(RuntimeError, match="chunk"):
        tiktok.publish_video(_clip(tmp_path), 0, "t", config)


def test_publish_video_polling_timeout_raises(tmp_path, monkeypatch):
    config = _config(tmp_path, publish_poll_timeout_seconds=0.05, publish_poll_interval_seconds=0.01)
    save_tokens("tiktok", _valid_tokens(), config)
    fake = _FakeRequests({
        tiktok._INIT_URL: [_init_response()],
        _UPLOAD_URL: [_FakeResponse(200)],
        tiktok._STATUS_URL: [_FakeResponse(200, {"data": {"status": "PROCESSING_UPLOAD"}})],
    })
    monkeypatch.setattr(tiktok, "requests", fake)

    with pytest.raises(TimeoutError):
        tiktok.publish_video(_clip(tmp_path), 0, "t", config)


def test_publish_video_platform_reported_failure_raises(tmp_path, monkeypatch):
    config = _config(tmp_path)
    save_tokens("tiktok", _valid_tokens(), config)
    fake = _FakeRequests({
        tiktok._INIT_URL: [_init_response()],
        _UPLOAD_URL: [_FakeResponse(200)],
        tiktok._STATUS_URL: [_FakeResponse(200, {"data": {"status": "FAILED"}})],
    })
    monkeypatch.setattr(tiktok, "requests", fake)

    with pytest.raises(RuntimeError, match="fallo"):
        tiktok.publish_video(_clip(tmp_path), 0, "t", config)


def test_requests_not_installed_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(tiktok, "requests", None)
    config = _config(tmp_path)
    with pytest.raises(RuntimeError, match="pip install"):
        tiktok.publish_video(_clip(tmp_path), 0, "t", config)


# ---------- refresh de tokens ----------

def test_publish_video_refreshes_expiring_token(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secret")
    expiring = TokenSet(
        access_token="old", refresh_token="ref",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    save_tokens("tiktok", expiring, config)

    fake = _FakeRequests({
        tiktok._TOKEN_URL: [_FakeResponse(200, {
            "access_token": "new", "refresh_token": "ref2", "expires_in": 3600, "open_id": "oid",
        })],
        tiktok._INIT_URL: [_init_response()],
        _UPLOAD_URL: [_FakeResponse(200)],
        tiktok._STATUS_URL: [_FakeResponse(200, {"data": {"status": "PUBLISH_COMPLETE"}})],
    })
    monkeypatch.setattr(tiktok, "requests", fake)

    result = tiktok.publish_video(_clip(tmp_path), 0, "t", config)

    assert result.success is True
    reloaded = load_tokens("tiktok", config)
    assert reloaded.access_token == "new"
    init_call = next(c for c in fake.calls if c[1] == tiktok._INIT_URL)
    assert init_call[2]["headers"]["Authorization"] == "Bearer new"


def test_refresh_token_missing_refresh_token_raises(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secret")
    monkeypatch.setattr(tiktok, "requests", _FakeRequests({}))
    tokens = TokenSet(access_token="tok", refresh_token=None, expires_at=datetime.now(timezone.utc))
    with pytest.raises(RuntimeError, match="auth tiktok"):
        tiktok.refresh_token(tokens, config)


def test_refresh_token_http_error_raises_actionable_message(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secret")
    fake = _FakeRequests({tiktok._TOKEN_URL: [_FakeResponse(401, text="invalid_grant")]})
    monkeypatch.setattr(tiktok, "requests", fake)
    tokens = TokenSet(access_token="tok", refresh_token="ref", expires_at=datetime.now(timezone.utc))
    with pytest.raises(RuntimeError, match="auth tiktok"):
        tiktok.refresh_token(tokens, config)


# ---------- authorize(): protección CSRF ----------

def test_authorize_rejects_state_mismatch(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secret")
    monkeypatch.setattr(tiktok, "requests", _FakeRequests({}))
    monkeypatch.setattr(
        tiktok, "wait_for_callback",
        lambda auth_url, port: OAuthCallbackResult(code="abc", state="state-que-no-coincide", error=None),
    )

    with pytest.raises(RuntimeError, match="state"):
        tiktok.authorize(config)


def test_authorize_raises_on_platform_error(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secret")
    monkeypatch.setattr(tiktok, "requests", _FakeRequests({}))
    monkeypatch.setattr(
        tiktok, "wait_for_callback",
        lambda auth_url, port: OAuthCallbackResult(code=None, state=None, error="access_denied"),
    )

    with pytest.raises(RuntimeError, match="access_denied"):
        tiktok.authorize(config)
