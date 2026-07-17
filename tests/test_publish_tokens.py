import stat
from datetime import datetime, timedelta, timezone

from clipengine.config import ClipConfig
from clipengine.publish.tokens import TokenSet, is_expiring_soon, load_tokens, save_tokens


def _config(tmp_path):
    return ClipConfig(work_dir=tmp_path / "work", output_dir=tmp_path / "output", publish_token_dir=tmp_path / "tokens")


def test_load_tokens_returns_none_when_missing(tmp_path):
    assert load_tokens("tiktok", _config(tmp_path)) is None


def test_save_and_load_roundtrip(tmp_path):
    config = _config(tmp_path)
    tokens = TokenSet(
        access_token="abc", refresh_token="def",
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc), extra={"open_id": "123"},
    )
    save_tokens("tiktok", tokens, config)

    loaded = load_tokens("tiktok", config)
    assert loaded == tokens


def test_save_tokens_sets_restrictive_permissions(tmp_path):
    config = _config(tmp_path)
    tokens = TokenSet(access_token="abc", refresh_token=None, expires_at=datetime.now(timezone.utc))
    save_tokens("instagram", tokens, config)

    path = config.publish_token_dir / "instagram.json"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_is_expiring_soon_true_when_within_margin():
    tokens = TokenSet(
        access_token="abc", refresh_token=None,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    assert is_expiring_soon(tokens, margin_seconds=300) is True


def test_is_expiring_soon_false_when_far_out():
    tokens = TokenSet(
        access_token="abc", refresh_token=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert is_expiring_soon(tokens, margin_seconds=300) is False
