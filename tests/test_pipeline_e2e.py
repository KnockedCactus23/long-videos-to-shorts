import json
import subprocess
from dataclasses import replace

from clipengine import pipeline as pipeline_module
from clipengine.candidates import RankedClip
from clipengine.config import ClipConfig
from clipengine.pipeline import run_pipeline
from clipengine.transcribe import Transcript, TranscriptSegment
from tests.fixtures.make_synthetic_media import make_synthetic_media

# Ráfagas de ruido (simulando aplausos) en la fixture: [10,20), [30,40), [50,60), ...
# es decir, centradas en 15, 35, 55, 75, 95, ...
EXPECTED_BURST_MIDPOINTS = [15, 35, 55, 75, 95, 115, 135, 155, 175]


def _ffprobe_dims(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    w, h = out.stdout.strip().split(",")
    return int(w), int(h)


def test_pipeline_end_to_end(tmp_path):
    fixture_path = make_synthetic_media(tmp_path / "synthetic_concert.mp4", duration=180)

    config = ClipConfig(
        clip_min_duration=8,
        clip_max_duration=15,
        clip_target_duration=10,
        num_clips=3,
        min_gap_seconds=15,
        peak_prominence=0.1,
        energy_weight=0.7,
        applause_weight=0.3,
        sample_rate=16000,
        output_width=270,
        output_height=480,
        crf=28,
        work_dir=tmp_path / "work",
        output_dir=tmp_path / "output",
    )

    output_dir = run_pipeline(str(fixture_path), config)

    clip_files = sorted(output_dir.glob("clip_*.mp4"))
    assert len(clip_files) == 3

    for clip_path in clip_files:
        width, height = _ffprobe_dims(clip_path)
        assert (width, height) == (270, 480)

    metadata_path = output_dir / "metadata.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text())
    assert len(metadata["clips"]) == 3

    for clip_meta in metadata["clips"]:
        peak_center = clip_meta["start"] + clip_meta["duration"] / 2
        assert any(abs(peak_center - expected) < 5 for expected in EXPECTED_BURST_MIDPOINTS)


def _fake_transcript(duration: int = 180) -> Transcript:
    segments = [
        TranscriptSegment(start=t, end=t + 5, text=f"linea en el segundo {t}")
        for t in range(0, duration, 5)
    ]
    return Transcript(segments=segments, text=" ".join(s.text for s in segments), language="es")


def _ai_config(tmp_path):
    return ClipConfig(
        clip_min_duration=8,
        clip_max_duration=15,
        clip_target_duration=10,
        num_clips=3,
        min_gap_seconds=15,
        peak_prominence=0.1,
        energy_weight=0.7,
        applause_weight=0.3,
        sample_rate=16000,
        output_width=270,
        output_height=480,
        crf=28,
        work_dir=tmp_path / "work",
        output_dir=tmp_path / "output",
        use_ai_layer=True,
        llm_provider="gemini",
    )


def test_pipeline_end_to_end_with_ai_layer_mocked(tmp_path, monkeypatch):
    fixture_path = make_synthetic_media(tmp_path / "synthetic_concert.mp4", duration=180)

    monkeypatch.setattr(pipeline_module, "transcribe_audio", lambda *a, **k: _fake_transcript())

    def fake_rank_and_title(transcript, candidates, config):
        return [
            RankedClip(candidate=c, title=f"IA Título {i + 1}", reason="Momento con mucha energía", ai_enhanced=True)
            for i, c in enumerate(candidates[: config.num_clips])
        ]

    monkeypatch.setattr(pipeline_module, "rank_and_title", fake_rank_and_title)

    config = _ai_config(tmp_path)
    output_dir = run_pipeline(str(fixture_path), config)

    clip_files = sorted(output_dir.glob("clip_*.mp4"))
    assert len(clip_files) == 3

    metadata = json.loads((output_dir / "metadata.json").read_text())
    assert metadata["ai_enhanced"] is True
    for i, clip_meta in enumerate(metadata["clips"]):
        assert clip_meta["title"] == f"IA Título {i + 1}"
        assert clip_meta["reason"] == "Momento con mucha energía"
        assert clip_meta["ai_enhanced"] is True

    # La generación de subtítulos (independiente de si ffmpeg pudo quemarlos:
    # requiere libass) debe haber corrido y escrito los .srt en work_dir.
    srt_files = sorted((tmp_path / "work").glob("clip_*.srt"))
    assert len(srt_files) == 3


def test_pipeline_ai_ranking_with_subtitles_disabled(tmp_path, monkeypatch):
    fixture_path = make_synthetic_media(tmp_path / "synthetic_concert.mp4", duration=180)

    monkeypatch.setattr(pipeline_module, "transcribe_audio", lambda *a, **k: _fake_transcript())

    def fake_rank_and_title(transcript, candidates, config):
        return [
            RankedClip(candidate=c, title=f"IA Título {i + 1}", reason="Momento con mucha energía", ai_enhanced=True)
            for i, c in enumerate(candidates[: config.num_clips])
        ]

    monkeypatch.setattr(pipeline_module, "rank_and_title", fake_rank_and_title)

    config = replace(_ai_config(tmp_path), burn_subtitles=False)
    output_dir = run_pipeline(str(fixture_path), config)

    metadata = json.loads((output_dir / "metadata.json").read_text())
    # La IA sigue rankeando/titulando: esto no depende de burn_subtitles.
    assert metadata["ai_enhanced"] is True
    for clip_meta in metadata["clips"]:
        assert clip_meta["title"].startswith("IA Título")
        assert clip_meta["has_subtitles"] is False

    # No se debe haber escrito ningún .srt.
    assert list((tmp_path / "work").glob("clip_*.srt")) == []


def test_pipeline_falls_back_when_llm_raises(tmp_path, monkeypatch):
    fixture_path = make_synthetic_media(tmp_path / "synthetic_concert.mp4", duration=180)

    monkeypatch.setattr(pipeline_module, "transcribe_audio", lambda *a, **k: _fake_transcript())
    # Simula que el dispatcher ya atrapó un fallo interno y devolvió None.
    monkeypatch.setattr(pipeline_module, "rank_and_title", lambda *a, **k: None)

    config = _ai_config(tmp_path)
    output_dir = run_pipeline(str(fixture_path), config)

    clip_files = sorted(output_dir.glob("clip_*.mp4"))
    assert len(clip_files) == 3

    metadata = json.loads((output_dir / "metadata.json").read_text())
    assert metadata["ai_enhanced"] is False
    for i, clip_meta in enumerate(metadata["clips"]):
        assert clip_meta["title"] == f"Momento destacado {i + 1}"
        assert clip_meta["ai_enhanced"] is False
