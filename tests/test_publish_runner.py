import pytest

from clipengine.config import ClipConfig
from clipengine.publish import runner
from clipengine.publish.status import load_status
from clipengine.publish.types import PublishResult


def _config(tmp_path):
    return ClipConfig(work_dir=tmp_path / "work", output_dir=tmp_path / "output")


def _clips(n=2):
    return [
        {"id": i, "file": f"clip_{i + 1:02d}.mp4", "title": f"Momento {i}", "reason": None}
        for i in range(n)
    ]


def test_publish_clips_unknown_platform_raises(tmp_path):
    with pytest.raises(ValueError, match="desconocida"):
        runner.publish_clips(_clips(), tmp_path, "myspace", _config(tmp_path))


def test_publish_clips_calls_target_and_saves_status(tmp_path, monkeypatch):
    calls = []

    def _fake_publish(clip_path, clip_id, caption, config):
        calls.append((clip_path, clip_id, caption))
        return PublishResult(platform="tiktok", clip_id=clip_id, success=True, external_id=f"ext{clip_id}")

    monkeypatch.setitem(runner._TARGETS, "tiktok", _fake_publish)

    results = runner.publish_clips(_clips(2), tmp_path, "tiktok", _config(tmp_path))

    assert len(results) == 2
    assert all(r.success for r in results)
    assert len(calls) == 2

    status = load_status(tmp_path)
    assert status[(0, "tiktok")].external_id == "ext0"
    assert status[(1, "tiktok")].external_id == "ext1"


def test_publish_clips_one_failure_does_not_block_others(tmp_path, monkeypatch):
    def _fake_publish(clip_path, clip_id, caption, config):
        if clip_id == 0:
            raise RuntimeError("token vencido")
        return PublishResult(platform="tiktok", clip_id=clip_id, success=True, external_id="ext1")

    monkeypatch.setitem(runner._TARGETS, "tiktok", _fake_publish)

    results = runner.publish_clips(_clips(2), tmp_path, "tiktok", _config(tmp_path))

    assert len(results) == 2
    by_id = {r.clip_id: r for r in results}
    assert by_id[0].success is False
    assert "token vencido" in by_id[0].error
    assert by_id[1].success is True


def test_publish_clips_skips_already_published_without_force(tmp_path, monkeypatch):
    calls = []

    def _fake_publish(clip_path, clip_id, caption, config):
        calls.append(clip_id)
        return PublishResult(platform="tiktok", clip_id=clip_id, success=True, external_id="ext")

    monkeypatch.setitem(runner._TARGETS, "tiktok", _fake_publish)

    runner.publish_clips(_clips(1), tmp_path, "tiktok", _config(tmp_path))
    assert calls == [0]

    calls.clear()
    results = runner.publish_clips(_clips(1), tmp_path, "tiktok", _config(tmp_path))
    assert calls == []  # no se volvió a llamar al target
    assert results[0].success is True
    assert results[0].external_id == "ext"


def test_publish_clips_force_republishes(tmp_path, monkeypatch):
    calls = []

    def _fake_publish(clip_path, clip_id, caption, config):
        calls.append(clip_id)
        return PublishResult(platform="tiktok", clip_id=clip_id, success=True, external_id="ext-new")

    monkeypatch.setitem(runner._TARGETS, "tiktok", _fake_publish)

    runner.publish_clips(_clips(1), tmp_path, "tiktok", _config(tmp_path))
    calls.clear()

    results = runner.publish_clips(_clips(1), tmp_path, "tiktok", _config(tmp_path), force=True)
    assert calls == [0]
    assert results[0].external_id == "ext-new"


def test_publish_clips_dry_run_never_calls_target_or_writes_status(tmp_path, monkeypatch):
    calls = []

    def _fake_publish(clip_path, clip_id, caption, config):
        calls.append(clip_id)
        return PublishResult(platform="tiktok", clip_id=clip_id, success=True)

    monkeypatch.setitem(runner._TARGETS, "tiktok", _fake_publish)

    results = runner.publish_clips(_clips(2), tmp_path, "tiktok", _config(tmp_path), dry_run=True)

    assert calls == []
    assert results == []
    assert not (tmp_path / "publish_status.json").exists()


def test_publish_clips_retries_previous_failure_without_force(tmp_path, monkeypatch):
    attempts = []

    def _fake_publish(clip_path, clip_id, caption, config):
        attempts.append(clip_id)
        if len(attempts) == 1:
            raise RuntimeError("fallo transitorio")
        return PublishResult(platform="tiktok", clip_id=clip_id, success=True, external_id="ext")

    monkeypatch.setitem(runner._TARGETS, "tiktok", _fake_publish)

    runner.publish_clips(_clips(1), tmp_path, "tiktok", _config(tmp_path))
    results = runner.publish_clips(_clips(1), tmp_path, "tiktok", _config(tmp_path))

    assert attempts == [0, 0]  # se reintentó sin --force porque el intento previo falló
    assert results[0].success is True
