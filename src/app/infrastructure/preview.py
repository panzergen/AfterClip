import hashlib
import json
import subprocess
from pathlib import Path

from app.infrastructure.process import CREATE_NO_WINDOW, get_media_metadata


class VideoPreviewExtractor:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root

    def extract(self, input_path: Path) -> tuple[Path, ...]:
        metadata = get_media_metadata(input_path)
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
        for index, frame in enumerate(frames):
            timestamp = 0 if index == 0 else duration * index / 9
            # Fast seeking can land past the final decodable frame; sample the
            # last second rather than the exact duration boundary.
            timestamp = min(timestamp, max(0, duration - 1.0))
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
                for created in frames:
                    created.unlink(missing_ok=True)
                raise RuntimeError(f"Could not extract preview frame {index + 1}: {result.stderr.strip()}")
        (cache_dir / "preview.json").write_text(json.dumps({"input": str(input_path), "frames": 10}), encoding="utf-8")
        return frames
