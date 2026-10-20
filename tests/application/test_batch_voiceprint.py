"""The batch worker must wire the voiceprint runtime into the service.

Regression: ``BatchWorker`` built its ``TranscriptionService`` without the
voiceprint store/embedder, so the per-job ``voiceprint_enabled`` flag was
silently ignored and no speaker identification happened in batch mode.
"""

from pathlib import Path
from typing import ClassVar

from app.application.batch import BatchJob, BatchStore
from app.workers.batch_worker import BatchWorker


class _RecordingService:
    """Captures the kwargs ``BatchWorker`` passes to ``TranscriptionService``."""

    instances: ClassVar[list["_RecordingService"]] = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.requests = []
        _RecordingService.instances.append(self)

    def run(self, request, on_event, cancel_token):
        self.requests.append(request)
        return True


def _patch_service(monkeypatch):
    _RecordingService.instances = []
    monkeypatch.setattr(
        "app.workers.batch_worker.TranscriptionService",
        _RecordingService,
    )
    return _RecordingService


def test_worker_passes_voiceprint_dependencies_to_the_service(monkeypatch, tmp_path: Path):
    _patch_service(monkeypatch)
    store = BatchStore(tmp_path / "batch_queue.json")
    worker = BatchWorker(
        store,
        voiceprint_store="store",
        voiceprint_embedder="embedder",
        voiceprint_identify_threshold=0.42,
        voiceprint_cluster_threshold=0.58,
    )
    job = BatchJob(id="1", input_path="a.mp4", output_dir="out", voiceprint_enabled=True)
    store.save([job])

    worker.run()

    assert len(_RecordingService.instances) == 1
    kwargs = _RecordingService.instances[0].kwargs
    assert kwargs["voiceprint_store"] == "store"
    assert kwargs["voiceprint_embedder"] == "embedder"
    assert kwargs["voiceprint_identify_threshold"] == 0.42
    assert kwargs["voiceprint_cluster_threshold"] == 0.58


def test_worker_keeps_the_voiceprint_flag_on_the_request(monkeypatch, tmp_path: Path):
    _patch_service(monkeypatch)
    store = BatchStore(tmp_path / "batch_queue.json")
    worker = BatchWorker(store)
    job = BatchJob(id="1", input_path="a.mp4", output_dir="out", voiceprint_enabled=True)
    store.save([job])

    worker.run()

    service = _RecordingService.instances[0]
    assert len(service.requests) == 1
    assert service.requests[0].voiceprint_enabled is True
