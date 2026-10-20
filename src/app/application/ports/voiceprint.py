from pathlib import Path
from typing import Protocol


class SpeakerEmbedder(Protocol):
    """Local speaker-embedding model (onnxruntime-backed in production)."""

    def embed(self, audio: Path) -> list[float]: ...


class VoiceprintStore(Protocol):
    """Persistence for enrolled speaker voiceprints (name -> embedding)."""

    def load(self) -> dict[str, list[float]]: ...

    def save(self, name: str, embedding: list[float]) -> None: ...

    def remove(self, name: str) -> None: ...
