from dataclasses import dataclass


@dataclass
class PublishResult:
    platform: str
    clip_id: int
    success: bool
    external_id: str | None = None
    permalink: str | None = None
    error: str | None = None
    published_at: str | None = None
