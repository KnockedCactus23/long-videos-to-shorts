import pytest

_CLIPENGINE_ENV_VARS = [
    "CLIP_MIN_DURATION", "CLIP_MAX_DURATION", "CLIP_TARGET_DURATION", "NUM_CLIPS",
    "MIN_GAP_SECONDS", "PEAK_PROMINENCE", "ENERGY_WEIGHT", "APPLAUSE_WEIGHT",
    "SAMPLE_RATE", "OUTPUT_WIDTH", "OUTPUT_HEIGHT", "VIDEO_CRF", "WORK_DIR", "OUTPUT_DIR",
    "USE_CHAT_SIGNAL", "USE_AI_LAYER", "LLM_PROVIDER", "WHISPER_MODEL_SIZE",
    "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE", "WHISPER_LANGUAGE", "GEMINI_MODEL",
    "GEMINI_API_KEY", "LLM_TIMEOUT_SECONDS", "AI_CANDIDATE_POOL_MULTIPLIER",
    "MAX_TRANSCRIPT_CHARS", "BURN_SUBTITLES",
]


@pytest.fixture(autouse=True)
def _isolated_config_env(monkeypatch):
    """El .env real del desarrollador (GEMINI_API_KEY, BURN_SUBTITLES, etc., cargado
    por config.py vía load_dotenv()) no debe filtrarse a los tests: ClipConfig() debe
    usar los defaults del código salvo que un test los fije explícitamente."""
    for name in _CLIPENGINE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
