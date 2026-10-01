import hashlib
import json
import logging
import subprocess
from pathlib import Path

from app.infrastructure.process import CREATE_NO_WINDOW, get_media_metadata

LOGGER = logging.getLogger(__name__)


class VideoPreviewExtractor:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self.last_metadata = {}

    def extract(self, input_path: Path) -> tuple[Path, ...]:
        metadata = get_media_metadata(input_path)
        self.last_metadata = metadata
        streams = metadata.get("streams", [])
        if not any(stream.get("type") == "video" for stream in streams):
            return ()
        cache_key = hashlib.sha256(
            f"{input_path.resolve()}|{input_path.stat().st_size}|{input_path.stat().st_mtime_ns}".encode()
        ).hexdigest()[:20]
        cache_dir = self.cache_root / cache_key
        frames = tuple(cache_dir / f"preview_{index:02d}.png" for index in range(1, 11))
        if all(frame.is_file() for frame in frames):
            return frames
        cache_dir.mkdir(parents=True, exist_ok=True)
        duration = float(metadata.get("duration", 0) or 0)
        if duration <= 0:
            return ()
        produced: list[Path] = []
        for index, frame in enumerate(frames):
            timestamp = 0 if index == 0 else duration * index / 9
            # Fast seeking can land past the final decodable frame; sample the
            # last second rather than the exact duration boundary.
            timestamp = min(timestamp, max(0, duration - 1.0))
            if self._extract_frame(input_path, frame, timestamp):
                produced.append(frame)
        if produced:
            (cache_dir / "preview.json").write_text(
                json.dumps({"input": str(input_path), "frames": len(produced)}),
                encoding="utf-8",
            )
        return tuple(produced)

    @staticmethod
    def _extract_frame(input_path: Path, frame: Path, timestamp: float) -> bool:
        """Extract one frame; False when the file can't provide it (skip, don't abort)."""
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(input_path), "-frames:v", "1", str(frame)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not frame.is_file():
            tail = (result.stderr or "").strip().splitlines()
            LOGGER.warning(
                "Preview frame at %.1fs could not be extracted; skipping. %s",
                timestamp,
                tail[-1] if tail else "ffmpeg produced no output",
            )
            return False
        return True
