import subprocess
import types
from pathlib import Path

from app.infrastructure.preview import VideoPreviewExtractor

VIDEO_METADATA = {"duration": 10, "streams": [{"type": "video", "codec": "h264", "width": 64, "height": 64}]}
AUDIO_METADATA = {"duration": 10, "streams": [{"type": "audio", "codec": "aac"}]}


def test_preview_extractor_creates_and_reuses_cached_frames(tmp_path, monkeypatch):
    calls = []

    def spying_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr("app.infrastructure.preview.get_media_metadata", lambda path: VIDEO_METADATA)
    monkeypatch.setattr("app.infrastructure.preview.subprocess", types.SimpleNamespace(run=spying_run, DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE))
    extractor = VideoPreviewExtractor(tmp_path / "cache")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fixture")
    frames = extractor.extract(video)
    assert len(frames) == 10
    assert all(frame.is_file() for frame in frames)
    assert len(calls) == 10
    cached = extractor.extract(video)
    assert cached == frames
    assert len(calls) == 10


def test_preview_extractor_returns_no_frames_for_audio(tmp_path, monkeypatch):
    monkeypatch.setattr("app.infrastructure.preview.get_media_metadata", lambda path: AUDIO_METADATA)
    extractor = VideoPreviewExtractor(tmp_path / "cache")
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fixture")
    assert extractor.extract(audio) == ()
