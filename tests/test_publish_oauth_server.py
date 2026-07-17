import threading
import time
import urllib.error
import urllib.request

import pytest

from clipengine.publish import oauth_server


def _simulate_browser_hit(port: int, path: str, delay: float = 0.2) -> None:
    def _hit():
        time.sleep(delay)
        urllib.request.urlopen(f"http://localhost:{port}{path}")

    threading.Thread(target=_hit, daemon=True).start()


def test_wait_for_callback_captures_code_and_state(monkeypatch):
    monkeypatch.setattr(oauth_server.webbrowser, "open", lambda url: None)
    _simulate_browser_hit(8913, "/callback?code=abc123&state=xyz")

    result = oauth_server.wait_for_callback("http://example.com/auth", 8913, timeout_seconds=5)

    assert result.code == "abc123"
    assert result.state == "xyz"
    assert result.error is None


def test_wait_for_callback_ignores_non_callback_paths(monkeypatch):
    """El navegador suele pedir /favicon.ico antes o después del redirect real — no
    debe confundirse con el callback de OAuth (que sí trae code/state)."""
    monkeypatch.setattr(oauth_server.webbrowser, "open", lambda url: None)

    def _hit_favicon_then_callback():
        time.sleep(0.1)
        try:
            urllib.request.urlopen("http://localhost:8914/favicon.ico")
        except urllib.error.HTTPError:
            pass
        time.sleep(0.1)
        urllib.request.urlopen("http://localhost:8914/callback?code=real&state=s1")

    threading.Thread(target=_hit_favicon_then_callback, daemon=True).start()

    result = oauth_server.wait_for_callback("http://example.com/auth", 8914, timeout_seconds=5)

    assert result.code == "real"
    assert result.state == "s1"


def test_wait_for_callback_captures_error_param(monkeypatch):
    monkeypatch.setattr(oauth_server.webbrowser, "open", lambda url: None)
    _simulate_browser_hit(8915, "/callback?error=access_denied&state=xyz")

    result = oauth_server.wait_for_callback("http://example.com/auth", 8915, timeout_seconds=5)

    assert result.error == "access_denied"
    assert result.code is None


def test_wait_for_callback_times_out_without_a_request(monkeypatch):
    monkeypatch.setattr(oauth_server.webbrowser, "open", lambda url: None)

    with pytest.raises(TimeoutError):
        oauth_server.wait_for_callback("http://example.com/auth", 8916, timeout_seconds=0.5)
