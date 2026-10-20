"""ONNX-backed local speaker embeddings (no PyTorch).

``speakeronnx`` + ``onnxruntime`` are optional dependencies: when they are not
installed the embedder is never constructed and the voiceprint feature is
disabled (mirroring how Whisper/FFmpeg are probed at runtime).
"""

import logging
import tempfile
from pathlib import Path

from app.infrastructure.audio import TARGET_RATE, read_wav_samples, to_16k_mono, write_wav_samples

LOGGER = logging.getLogger(__name__)

DEFAULT_MODEL = "redimnet-b2"


def voiceprints_available() -> bool:
    try:
        import speakeronnx  # noqa: F401

        return True
    except ImportError:
        return False


class SpeakerOnnxEmbedder:
    """Wrap ``speakeronnx.SpeakerEmbedder`` behind a simple ``embed`` API."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._embedder = None

    def _load(self):
        if self._embedder is None:
            import speakeronnx

            self._embedder = speakeronnx.SpeakerEmbedder(model=self.model)
        return self._embedder

    def embed(self, audio_path: Path) -> list[float]:
        """Embed a WAV file (any sample rate/channels) as a 16 kHz mono float list."""
        samples, rate, channels = read_wav_samples(audio_path)
        return self._embed(to_16k_mono(samples, rate, channels))

    def embed_samples(
        self, samples: list[float], sample_rate: int = TARGET_RATE, work_dir: Path | None = None
    ) -> list[float]:
        return self._embed(to_16k_mono(samples, sample_rate, 1), work_dir)

    def _embed(self, samples: list[float], work_dir: Path | None = None) -> list[float]:
        directory = work_dir or Path(tempfile.gettempdir())
        directory.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(suffix=".wav", dir=directory, delete=False)
        temp_path = Path(handle.name)
        handle.close()
        try:
            write_wav_samples(temp_path, samples)
            result = self._load().embed(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)
        return [float(value) for value in result]
