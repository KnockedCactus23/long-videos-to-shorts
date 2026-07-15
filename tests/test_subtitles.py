from clipengine.subtitles import _format_srt_timestamp, slice_transcript, write_srt
from clipengine.transcribe import Transcript, TranscriptSegment


def test_format_srt_timestamp():
    assert _format_srt_timestamp(0.5) == "00:00:00,500"
    assert _format_srt_timestamp(65.25) == "00:01:05,250"
    assert _format_srt_timestamp(3661.001) == "01:01:01,001"


def test_slice_transcript_filters_and_rebases():
    transcript = Transcript(
        segments=[
            TranscriptSegment(start=5, end=8, text="hola mundo"),
            TranscriptSegment(start=9, end=25, text="cruza el borde"),
            TranscriptSegment(start=100, end=105, text="fuera de rango"),
        ],
        text="...",
    )

    sliced = slice_transcript(transcript, start=6, end=20)

    assert len(sliced) == 2
    assert sliced[0].start == 0
    assert sliced[0].end == 2
    assert sliced[0].text == "hola mundo"
    assert sliced[1].start == 3
    assert sliced[1].end == 14


def test_slice_transcript_excludes_segments_entirely_outside_window():
    transcript = Transcript(segments=[TranscriptSegment(start=0, end=5, text="antes")], text="antes")
    sliced = slice_transcript(transcript, start=10, end=20)
    assert sliced == []


def test_write_srt_creates_valid_file(tmp_path):
    segments = [TranscriptSegment(start=0, end=2, text="hola mundo")]
    out_path = write_srt(segments, tmp_path / "clip_01.srt")

    assert out_path is not None
    content = out_path.read_text()
    assert "1\n00:00:00,000 --> 00:00:02,000\nhola mundo" in content


def test_write_srt_returns_none_for_empty_segments(tmp_path):
    result = write_srt([], tmp_path / "clip_01.srt")
    assert result is None
    assert not (tmp_path / "clip_01.srt").exists()
