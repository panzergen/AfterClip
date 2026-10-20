"""Minimal WAV helpers for speaker-voiceprint audio.

The prepared transcript audio is 16 kHz mono PCM (s16le), but the voiceprint
path also accepts a raw ``.wav`` passthrough, so these helpers decode, downmix
and resample to a common 16 kHz mono float32 representation before embedding.
"""

import array
import wave
from pathlib import Path

TARGET_RATE = 16000


def read_wav_samples(path: Path) -> tuple[list[float], int, int]:
    """Return ``(samples, sample_rate, channels)`` as float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if sample_width == 1:
        samples = [(byte - 128) / 128.0 for byte in raw]
    elif sample_width == 2:
        samples = [value / 32768.0 for value in array.array("h", raw)]
    elif sample_width == 4:
        samples = [value / 2147483648.0 for value in array.array("i", raw)]
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")
    return samples, rate, channels


def to_16k_mono(samples: list[float], rate: int, channels: int) -> list[float]:
    """Downmix to mono and resample to 16 kHz (identity when already there)."""
    if channels > 1:
        samples = _downmix(samples, channels)
    if rate != TARGET_RATE:
        samples = resample(samples, rate, TARGET_RATE)
    return samples


def _downmix(samples: list[float], channels: int) -> list[float]:
    frames = len(samples) // channels
    return [
        sum(samples[frame * channels + channel] for channel in range(channels)) / channels
        for frame in range(frames)
    ]


def resample(samples: list[float], src_rate: int, dst_rate: int) -> list[float]:
    if src_rate == dst_rate or not samples:
        return list(samples)
    ratio = src_rate / dst_rate
    output_length = max(1, round(len(samples) / ratio))
    resampled: list[float] = []
    for index in range(output_length):
        position = index * ratio
        lower = int(position)
        fraction = position - lower
        upper = min(lower + 1, len(samples) - 1)
        resampled.append(samples[lower] * (1.0 - fraction) + samples[upper] * fraction)
    return resampled


def slice_samples(
    samples: list[float], start_seconds: float, end_seconds: float, rate: int
) -> list[float]:
    start = max(0, min(len(samples), int(start_seconds * rate)))
    end = max(0, min(len(samples), int(end_seconds * rate)))
    return samples[start:end]


def write_wav_samples(path: Path, samples: list[float], rate: int = TARGET_RATE) -> None:
    encoded = array.array("h", (int(max(-1.0, min(1.0, value)) * 32767.0) for value in samples))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(encoded.tobytes())
