"""Post-job speaker enrollment: name the ``Speaker N`` clusters a job found.

The controller loads the job's ``Voiceprints.json`` sidecar (segment embeddings
and their clusters), lets the user tune the cluster threshold live, listen to a
sample of each group, and name each group (enrolling that group's centroid as a
global voiceprint). The actual reprocess is delegated to the session so it can
reuse the job's request and thresholds.
"""

import logging
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from app.application.voiceprints import (
    DEFAULT_CLUSTER_THRESHOLD,
    DEFAULT_IDENTIFY_THRESHOLD,
    SpeakerSegment,
    analyse_speakers,
    load_voiceprint_sidecar,
)
from app.infrastructure.voiceprints import JsonVoiceprintStore

LOGGER = logging.getLogger(__name__)


def _recognized_speakers(intervals) -> list[dict]:
    counts = Counter(
        interval.speaker
        for interval in intervals
        if interval.speaker and not interval.speaker.startswith("Speaker ")
    )
    return [{"name": name, "segments": count} for name, count in counts.most_common()]


class VoiceprintEnrollmentController(QObject):
    """Backs the post-job 'name the speakers' dialog."""

    speakersChanged = Signal()
    recognizedChanged = Signal()
    visibleChanged = Signal()
    statusChanged = Signal()
    clusterThresholdChanged = Signal()
    reprocessRequested = Signal()

    def __init__(self, store: JsonVoiceprintStore | None = None, parent=None):
        super().__init__(parent)
        self._store = store or JsonVoiceprintStore()
        self._speakers: list[dict] = []
        self._recognized: list[dict] = []
        self._clusters = []
        self._segments: list[SpeakerSegment] = []
        self._visible = False
        self._status = ""
        self._input_path = ""
        self._clip_start = 0.0
        self._cluster_threshold = DEFAULT_CLUSTER_THRESHOLD
        self._player = None
        self._audio_output = None
        self._stop_timer = None

    def _get_visible(self) -> bool:
        return self._visible

    def _get_speakers(self) -> list:
        return self._speakers

    def _get_recognized(self) -> list:
        return self._recognized

    def _get_status(self) -> str:
        return self._status

    def _get_cluster_threshold(self) -> float:
        return self._cluster_threshold

    def _set_cluster_threshold(self, value) -> None:
        self._cluster_threshold = float(value)
        self._recluster()
        self.clusterThresholdChanged.emit()

    visible = Property(bool, _get_visible, notify=visibleChanged)
    speakers = Property("QVariantList", _get_speakers, notify=speakersChanged)
    recognized = Property("QVariantList", _get_recognized, notify=recognizedChanged)
    statusText = Property(str, _get_status, notify=statusChanged)
    clusterThreshold = Property(
        float,
        _get_cluster_threshold,
        _set_cluster_threshold,
        notify=clusterThresholdChanged,
    )

    def prepare(self, job_dir: str, input_path: str = "", clip_start: float = 0.0) -> None:
        """Load a finished job's embeddings and open the dialog when relevant."""
        path = Path(job_dir)
        segments, _clusters = load_voiceprint_sidecar(path / "Voiceprints.json")
        self._segments = segments
        self._input_path = input_path
        self._clip_start = float(clip_start or 0.0)
        self._cluster_threshold = DEFAULT_CLUSTER_THRESHOLD
        self._recluster()
        self._status = ""
        self.statusChanged.emit()
        if self._clusters:
            self._visible = True
            self.visibleChanged.emit()

    def _apply_clusters(self, clusters) -> None:
        self._clusters = clusters
        self._speakers = [
            {"label": cluster.label, "name": "", "segments": len(cluster.segments)}
            for cluster in clusters
        ]
        self.speakersChanged.emit()

    def _recluster(self) -> None:
        voiceprints = self._store.load()
        analysis = analyse_speakers(
            [(segment.start_ms, segment.end_ms) for segment in self._segments],
            [segment.embedding for segment in self._segments],
            voiceprints,
            DEFAULT_IDENTIFY_THRESHOLD,
            self._cluster_threshold,
        )
        self._recognized = _recognized_speakers(analysis.intervals)
        self.recognizedChanged.emit()
        self._apply_clusters(analysis.clusters)

    @Slot(int, str)
    def setName(self, index: int, name: str) -> None:
        if 0 <= index < len(self._speakers):
            self._speakers[index]["name"] = str(name)

    @Slot(int)
    def enroll(self, index: int) -> None:
        if not (0 <= index < len(self._clusters)):
            return
        name = str(self._speakers[index].get("name", "")).strip()
        if not name:
            self._set_status("Enter a name for this speaker first.")
            return
        self._save(name, self._clusters[index].centroid)
        self._speakers[index]["name"] = ""
        self.speakersChanged.emit()
        self._set_status(f"Enrolled '{name}' from {self._clusters[index].label}.")

    def _enroll_named(self) -> int:
        """Persist every row that already has a name typed (for one-click flow)."""
        count = 0
        for index, cluster in enumerate(self._clusters):
            name = str(self._speakers[index].get("name", "")).strip()
            if name:
                self._save(name, cluster.centroid)
                count += 1
        return count

    def _save(self, name: str, centroid) -> None:
        try:
            self._store.save(name, list(centroid))
        except Exception as error:
            LOGGER.error("Failed to enroll voiceprint '%s': %s", name, error)
            self._set_status(f"Could not enroll '{name}': {error}")

    @Slot(int)
    def playSegment(self, index: int) -> None:
        """Play a representative segment of this cluster from the original recording."""
        if not (0 <= index < len(self._clusters)) or not self._input_path:
            return
        segments = self._clusters[index].segments
        if not segments:
            return
        start_ms, end_ms = max(segments, key=lambda span: span[1] - span[0])
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except Exception as error:  # multimedia unavailable (e.g. offscreen)
            LOGGER.warning("Cannot play segment: %s", error)
            return
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._audio_output.setVolume(0.8)
            self._player.setAudioOutput(self._audio_output)
            self._stop_timer = QTimer(self)
            self._stop_timer.setSingleShot(True)
            self._stop_timer.timeout.connect(self._player.stop)
        self._player.setSource(QUrl.fromLocalFile(self._input_path))
        self._player.setPosition(int(self._clip_start * 1000) + start_ms)
        self._player.play()
        self._stop_timer.start(max(500, end_ms - start_ms))

    @Slot()
    def stopSegment(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.stop()
        if self._player is not None:
            self._player.stop()

    @Slot()
    def reprocess(self) -> None:
        self._enroll_named()
        self.reprocessRequested.emit()
        self.close()

    @Slot()
    def close(self) -> None:
        self._visible = False
        self.visibleChanged.emit()

    def _set_status(self, text: str) -> None:
        self._status = text
        self.statusChanged.emit()
