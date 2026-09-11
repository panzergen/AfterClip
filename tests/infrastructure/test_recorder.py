import subprocess

import pytest

import app.infrastructure.recorder as recorder_module
from app.infrastructure.recorder import AudioRecorder


class FakePopen:
    returncode = 0

    def __init__(self, stderr_lines):
        self.written = []
        self.stdin = self
        self.stderr = iter(stderr_lines)

    def write(self, data):
        self.written.append(data)

    def flush(self):
        pass

    def poll(self):
        return 1 if self.written else None

    def wait(self, timeout=None):
        return 0


def test_recorder_drains_stderr_and_surfaces_failure(tmp_path, monkeypatch):
    fake = FakePopen(["device busy\n", "cannot open\n"])
    monkeypatch.setattr(recorder_module.subprocess, "Popen", lambda *args, **kwargs: fake)
    recorder = AudioRecorder()
    recorder.start(tmp_path / "out.wav", True, False)
    import time

    for _ in range(100):
        if recorder.stderr_lines:
            break
        time.sleep(0.01)
    with pytest.raises(RuntimeError, match="device busy") as error:
        recorder.stop()
    assert "cannot open" in str(error.value)
    assert recorder.stderr_lines == ["device busy\n", "cannot open\n"]
    assert fake.written == ["q\n"]


def test_supports_system_audio_is_cached(monkeypatch):
    recorder_module.supports_system_audio.cache_clear()
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(1)
        return subprocess.CompletedProcess([], 0, "wasapi supported here", "")

    monkeypatch.setattr(recorder_module.subprocess, "run", fake_run)
    try:
        assert recorder_module.supports_system_audio() is True
        assert recorder_module.supports_system_audio() is True
        assert len(calls) == 1
    finally:
        recorder_module.supports_system_audio.cache_clear()


def test_recorder_stop_grace_period_long_enough_for_live_audio():
    assert recorder_module.RECORD_STOP_GRACE_SECONDS >= 20
