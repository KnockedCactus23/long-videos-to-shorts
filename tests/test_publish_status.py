from clipengine.publish.status import load_status, save_status
from clipengine.publish.types import PublishResult


def test_load_status_empty_when_missing(tmp_path):
    assert load_status(tmp_path) == {}


def test_save_and_load_roundtrip(tmp_path):
    records = {
        (0, "tiktok"): PublishResult(platform="tiktok", clip_id=0, success=True, external_id="pid1"),
        (0, "instagram"): PublishResult(platform="instagram", clip_id=0, success=False, error="boom"),
    }
    save_status(tmp_path, records)

    loaded = load_status(tmp_path)
    assert loaded == records


def test_save_overwrites_previous_content(tmp_path):
    save_status(tmp_path, {(0, "tiktok"): PublishResult(platform="tiktok", clip_id=0, success=True)})
    save_status(tmp_path, {(1, "tiktok"): PublishResult(platform="tiktok", clip_id=1, success=True)})

    loaded = load_status(tmp_path)
    assert (0, "tiktok") not in loaded
    assert (1, "tiktok") in loaded
