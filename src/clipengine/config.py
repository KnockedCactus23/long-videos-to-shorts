from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _b(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() == "true"


def _s(name: str, default: str) -> str:
    return os.getenv(name, default)


def _lang(name: str, default: str) -> str | None:
    value = os.getenv(name, default).strip()
    return None if value.lower() in ("", "auto") else value


@dataclass
class ClipConfig:
    clip_min_duration: float = field(default_factory=lambda: _f("CLIP_MIN_DURATION", 20))
    clip_max_duration: float = field(default_factory=lambda: _f("CLIP_MAX_DURATION", 60))
    clip_target_duration: float = field(default_factory=lambda: _f("CLIP_TARGET_DURATION", 40))
    num_clips: int = field(default_factory=lambda: _i("NUM_CLIPS", 5))
    min_gap_seconds: float = field(default_factory=lambda: _f("MIN_GAP_SECONDS", 45))
    peak_prominence: float = field(default_factory=lambda: _f("PEAK_PROMINENCE", 0.15))
    energy_weight: float = field(default_factory=lambda: _f("ENERGY_WEIGHT", 0.7))
    applause_weight: float = field(default_factory=lambda: _f("APPLAUSE_WEIGHT", 0.3))
    sample_rate: int = field(default_factory=lambda: _i("SAMPLE_RATE", 16000))
    output_width: int = field(default_factory=lambda: _i("OUTPUT_WIDTH", 1080))
    output_height: int = field(default_factory=lambda: _i("OUTPUT_HEIGHT", 1920))
    crf: int = field(default_factory=lambda: _i("VIDEO_CRF", 18))
    work_dir: Path = field(default_factory=lambda: Path(os.getenv("WORK_DIR", "./work")))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./output")))

    # Señal de chat: en standby (ver CLAUDE.md sección 8), no implementada.
    use_chat_signal: bool = field(default_factory=lambda: _b("USE_CHAT_SIGNAL", False))

    # Capa de IA opcional (Fase 2): transcripción + adaptador LLM. Ignorados si use_ai_layer=False.
    use_ai_layer: bool = field(default_factory=lambda: _b("USE_AI_LAYER", False))
    llm_provider: str | None = field(default_factory=lambda: os.getenv("LLM_PROVIDER"))
    whisper_model_size: str = field(default_factory=lambda: _s("WHISPER_MODEL_SIZE", "small"))
    whisper_device: str = field(default_factory=lambda: _s("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(default_factory=lambda: _s("WHISPER_COMPUTE_TYPE", "int8"))
    # Idioma fijo para la transcripción (evita que Whisper autodetecte mal el idioma a
    # partir de un intro instrumental/aplausos sin habla). "auto" o vacío = autodetectar.
    whisper_language: str | None = field(default_factory=lambda: _lang("WHISPER_LANGUAGE", "es"))
    gemini_model: str = field(default_factory=lambda: _s("GEMINI_MODEL", "gemini-2.5-flash"))
    llm_timeout_seconds: float = field(default_factory=lambda: _f("LLM_TIMEOUT_SECONDS", 120))
    ai_candidate_pool_multiplier: int = field(default_factory=lambda: _i("AI_CANDIDATE_POOL_MULTIPLIER", 3))
    max_transcript_chars: int = field(default_factory=lambda: _i("MAX_TRANSCRIPT_CHARS", 20000))
    # Quemar subtítulos es independiente de use_ai_layer: con use_ai_layer=True y
    # burn_subtitles=False se sigue transcribiendo/rankeando con el LLM, pero no se
    # genera ni quema el .srt.
    burn_subtitles: bool = field(default_factory=lambda: _b("BURN_SUBTITLES", True))

    # Publicación automática (Fase 3): redes de seguridad además de la elección explícita
    # de plataforma en `clipengine publish <plataforma>` — en False, el comando se niega
    # a publicar aunque se lo pidan.
    publish_tiktok: bool = field(default_factory=lambda: _b("PUBLISH_TIKTOK", False))
    publish_instagram: bool = field(default_factory=lambda: _b("PUBLISH_INSTAGRAM", False))
    publish_poll_interval_seconds: float = field(default_factory=lambda: _f("PUBLISH_POLL_INTERVAL_SECONDS", 15))
    publish_poll_timeout_seconds: float = field(default_factory=lambda: _f("PUBLISH_POLL_TIMEOUT_SECONDS", 300))
    # Puerto del servidor local que recibe el callback de OAuth durante `clipengine auth
    # <plataforma>` — debe coincidir con el redirect URI registrado en el dashboard de
    # cada app (TikTok for Developers / Meta for Developers).
    publish_oauth_port: int = field(default_factory=lambda: _i("PUBLISH_OAUTH_PORT", 8912))
    publish_token_dir: Path = field(default_factory=lambda: Path(os.getenv(
        "PUBLISH_TOKEN_DIR", str(Path.home() / ".config" / "clipengine" / "tokens")
    )))
