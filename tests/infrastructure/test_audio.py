from app.infrastructure.audio import (
    TARGET_RATE,
    read_wav_samples,
    resample,
    slice_samples,
    to_16k_mono,
    write_wav_samples,
)


def test_write_read_round_trip(tmp_path):
    path = tmp_path / "clip.wav"
    samples = [0.0, 0.25, -0.5, 1.0, -1.0]
    write_wav_samples(path, samples)
    read, rate, channels = read_wav_samples(path)
    assert rate == TARGET_RATE
    assert channels == 1
    assert len(read) == len(samples)
    assert all(abs(a - b) < 0.001 for a, b in zip(read, samples, strict=True))


def test_slice_samples_bounds():
    samples = list(range(1000))
    assert slice_samples(samples, 0.0, 0.5, 1000) == samples[:500]
    assert slice_samples(samples, -1.0, 0.5, 1000) == samples[:500]
    assert slice_samples(samples, 0.9, 5.0, 1000) == samples[900:]


def test_resample_preserves_length_ratio():
    samples = [0.0, 1.0, 0.0, -1.0] * 10
    down = resample(samples, 16000, 8000)
    assert len(down) == len(samples) // 2
    up = resample(samples, 8000, 16000)
    assert len(up) == len(samples) * 2


def test_to_16k_mono_downmixes_stereo():
    # Interleaved stereo: left = 1.0, right = 0.0 -> mono 0.5
    stereo = [1.0, 0.0] * 100
    mono = to_16k_mono(stereo, TARGET_RATE, 2)
    assert len(mono) == 100
    assert all(abs(value - 0.5) < 1e-9 for value in mono)


def test_read_wav_samples_rejects_unknown_width(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"not a wav")
    try:
        read_wav_samples(path)
    except Exception:
        pass
    else:
        raise AssertionError("malformed WAV must raise")


def test_to_16k_mono_resamples_when_needed():
    samples = [0.0, 1.0, 0.0, -1.0]
    result = to_16k_mono(samples, 8000, 1)
    assert len(result) == 8
