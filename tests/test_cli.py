import json

import pytest

from clipengine import cli
from clipengine.publish.types import PublishResult


# ---------- run ----------

def test_run_delegates_to_pipeline_with_overrides(tmp_path, monkeypatch):
    captured = {}

    def _fake_run_pipeline(input_source, config):
        captured["input"] = input_source
        captured["config"] = config
        return tmp_path / "output"

    monkeypatch.setattr(cli, "run_pipeline", _fake_run_pipeline)

    args = cli.build_parser().parse_args([
        "run", "--input", "<url>", "--output-dir", str(tmp_path / "out"), "--num-clips", "3",
    ])
    cli._run(args)

    assert captured["input"] == "<url>"
    assert captured["config"].num_clips == 3
    assert captured["config"].output_dir == tmp_path / "out"


def test_run_without_overrides_uses_config_defaults(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "run_pipeline", lambda src, config: captured.setdefault("config", config) or tmp_path)

    args = cli.build_parser().parse_args(["run", "--input", "<url>"])
    cli._run(args)

    assert captured["config"].num_clips == 5  # default de ClipConfig, sin override


# ---------- publish ----------

def _write_metadata(output_dir, clips):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(json.dumps({"clips": clips}))


def test_publish_requires_existing_metadata(tmp_path):
    args = cli.build_parser().parse_args(["publish", "tiktok", "--output-dir", str(tmp_path / "missing")])
    with pytest.raises(SystemExit, match="metadata.json"):
        cli._publish(args)


def test_publish_refuses_when_platform_flag_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("PUBLISH_TIKTOK", raising=False)
    output_dir = tmp_path / "out"
    _write_metadata(output_dir, [{"id": 0, "file": "clip_01.mp4", "title": "t", "reason": None}])

    args = cli.build_parser().parse_args(["publish", "tiktok", "--output-dir", str(output_dir)])
    with pytest.raises(SystemExit, match="PUBLISH_TIKTOK"):
        cli._publish(args)


def test_publish_dry_run_allowed_even_with_flag_disabled(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    _write_metadata(output_dir, [{"id": 0, "file": "clip_01.mp4", "title": "t", "reason": None}])

    calls = []
    monkeypatch.setattr(
        cli.runner, "publish_clips",
        lambda clips, out, platform, config, force, dry_run: calls.append((clips, platform, dry_run)) or [],
    )

    args = cli.build_parser().parse_args(["publish", "tiktok", "--output-dir", str(output_dir), "--dry-run"])
    cli._publish(args)  # no debe lanzar SystemExit aunque PUBLISH_TIKTOK esté en false

    assert calls[0][2] is True


def test_publish_converts_1_indexed_clips_to_0_indexed_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISH_TIKTOK", "true")
    output_dir = tmp_path / "out"
    _write_metadata(output_dir, [
        {"id": 0, "file": "clip_01.mp4", "title": "a", "reason": None},
        {"id": 1, "file": "clip_02.mp4", "title": "b", "reason": None},
        {"id": 2, "file": "clip_03.mp4", "title": "c", "reason": None},
    ])

    captured = {}

    def _fake_publish_clips(clips, out, platform, config, force, dry_run):
        captured["clips"] = clips
        return [PublishResult(platform="tiktok", clip_id=c["id"], success=True) for c in clips]

    monkeypatch.setattr(cli.runner, "publish_clips", _fake_publish_clips)

    args = cli.build_parser().parse_args([
        "publish", "tiktok", "--output-dir", str(output_dir), "--clips", "1,3",
    ])
    cli._publish(args)

    assert [c["id"] for c in captured["clips"]] == [0, 2]  # 1,3 (1-indexado) -> 0,2 (id de metadata.json)


def test_publish_exits_nonzero_when_any_clip_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISH_TIKTOK", "true")
    output_dir = tmp_path / "out"
    _write_metadata(output_dir, [{"id": 0, "file": "clip_01.mp4", "title": "t", "reason": None}])

    monkeypatch.setattr(
        cli.runner, "publish_clips",
        lambda clips, out, platform, config, force, dry_run: [
            PublishResult(platform="tiktok", clip_id=0, success=False, error="boom")
        ],
    )

    args = cli.build_parser().parse_args(["publish", "tiktok", "--output-dir", str(output_dir)])
    with pytest.raises(SystemExit) as exc_info:
        cli._publish(args)
    assert exc_info.value.code == 1


# ---------- auth ----------

def test_auth_calls_the_right_platform_module(monkeypatch):
    called = {}
    monkeypatch.setattr(cli.tiktok, "authorize", lambda config: called.setdefault("platform", "tiktok"))
    monkeypatch.setattr(cli.instagram, "authorize", lambda config: called.setdefault("platform", "instagram"))

    args = cli.build_parser().parse_args(["auth", "instagram"])
    cli._auth(args)

    assert called["platform"] == "instagram"
