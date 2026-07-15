import pytest

from clipengine import ingest


class _FakeYoutubeDL:
    last_opts = None

    def __init__(self, opts):
        _FakeYoutubeDL.last_opts = opts
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        return {"id": "abc123", "ext": "webm"}

    def prepare_filename(self, info):
        return self.opts["outtmpl"].replace("%(ext)s", info["ext"])


class _FakeYtDlpModule:
    YoutubeDL = _FakeYoutubeDL


def test_is_url():
    assert ingest.is_url("https://youtu.be/xyz") is True
    assert ingest.is_url("http://example.com/video.mp4") is True
    assert ingest.is_url("/local/path/video.mp4") is False
    assert ingest.is_url("video.mp4") is False


def test_resolve_local_input_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest.resolve_local_input(str(tmp_path / "no_existe.mp4"))


def test_resolve_local_input_existing(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    assert ingest.resolve_local_input(str(f)) == f


def test_download_audio_only_uses_bestaudio_format_only(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "yt_dlp", _FakeYtDlpModule)

    result = ingest.download_audio_only("https://youtu.be/xyz", tmp_path)

    opts = _FakeYoutubeDL.last_opts
    assert opts["format"] == "bestaudio/best"
    assert "download_ranges" not in opts
    assert result == tmp_path / "source_audio.webm"


def test_download_video_segment_requests_only_the_given_range(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "yt_dlp", _FakeYtDlpModule)
    dest = tmp_path / "clip_01_src.mp4"

    result = ingest.download_video_segment("https://youtu.be/xyz", 10.0, 20.0, dest)

    opts = _FakeYoutubeDL.last_opts
    assert opts["format"] == "bv*+ba/b"
    assert opts["merge_output_format"] == "mp4"
    assert opts["force_keyframes_at_cuts"] is True
    ranges = list(opts["download_ranges"]({"duration": 999}, None))
    assert ranges == [{"start_time": 10.0, "end_time": 20.0}]
    assert result == dest
