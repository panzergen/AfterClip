"""Completion-sound playback via a non-blocking ``QSoundEffect``.

The effect is created lazily and kept alive on the instance so a short WAV can
finish playing without being garbage-collected mid-playback.
"""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect


class NotificationSound:
    def __init__(self):
        self._effect = None

    def _ensure(self) -> QSoundEffect:
        if self._effect is None:
            self._effect = QSoundEffect()
            self._effect.setVolume(0.85)
        return self._effect

    def play(self, path: Path | str) -> None:
        effect = self._ensure()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.play()
