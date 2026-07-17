import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from clipengine.config import ClipConfig


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    extra: dict = field(default_factory=dict)  # ej. open_id (TikTok), ig_user_id (Instagram)


def _token_path(platform: str, config: ClipConfig) -> Path:
    return config.publish_token_dir / f"{platform}.json"


def load_tokens(platform: str, config: ClipConfig) -> TokenSet | None:
    path = _token_path(platform, config)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        extra=data.get("extra", {}),
    )


def save_tokens(platform: str, tokens: TokenSet, config: ClipConfig) -> None:
    path = _token_path(platform, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at.isoformat(),
        "extra": tokens.extra,
    }
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)  # son las credenciales de posteo de la cuenta real


def is_expiring_soon(tokens: TokenSet, margin_seconds: float = 300) -> bool:
    remaining = (tokens.expires_at - datetime.now(timezone.utc)).total_seconds()
    return remaining <= margin_seconds
