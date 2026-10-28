from pathlib import Path

from app.application.batch import (
    BatchStore,
    new_batch_job,
    run_batch,
)
from app.application.cancellation import CancellationToken
from app.domain.models import TranscriptionRequest


def make_job(name="a.mp4", status="pending", **overrides):
    job = new_batch_job(Path(name), Path("out"), model="tiny")
    job.status = status
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


def test_store_round_trip_preserves_jobs(tmp_path: Path):
    store = BatchStore(tmp_path / "batch_queue.json")
    job = make_job()
    job.frame_modes = ("interval", "scene")
    job.highlight_times = (1.5, 2.5)
    store.save([job])
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].frame_modes == ("interval", "scene")
    assert loaded[0].highlight_times == (1.5, 2.5)


def test_store_recovers_running_jobs_to_pending_on_load(tmp_path: Path):
    store = BatchStore(tmp_path / "batch_queue.json")
    store.save([make_job(status="running"), make_job("b.mp4", status="completed")])
    loaded = store.load()
    assert loaded[0].status == "pending"  # T26b: crashed mid-run
    assert loaded[1].status == "completed"


def test_to_request_round_trip():
    job = make_job(
        extract_frames=True,
        frame_modes=("scene",),
        analyze_text=True,
        text_provider_name="gemini",
        text_model="m",
    )
    request = job.to_request()
    assert isinstance(request, TranscriptionRequest)
    assert request.frame_modes == ("scene",)
    assert request.analyze_text is True and request.analysis_model == "m"


def test_run_batch_continues_after_individual_failure(tmp_path: Path):
    store = BatchStore(tmp_path / "batch_queue.json")
    jobs = [make_job("a.mp4"), make_job("b.mp4"), make_job("c.mp4")]
    store.save(jobs)
    events = []

    def runner(job, on_event, token):
        if job.display_name == "b.mp4":
            raise RuntimeError("whisper exploded")

    run_batch(store.load(), store, runner, events.append, CancellationToken())
    statuses = {job.display_name: job.status for job in store.load()}
    assert statuses == {"a.mp4": "completed", "b.mp4": "failed", "c.mp4": "completed"}
    assert any("failed" in event for event in events)


def test_run_batch_cancel_keeps_pending_jobs(tmp_path: Path):
    store = BatchStore(tmp_path / "batch_queue.json")
    jobs = [make_job("a.mp4"), make_job("b.mp4"), make_job("c.mp4")]
    store.save(jobs)
    events = []

    def runner(job, on_event, token):
        token.cancel()  # user cancels during the first job
        raise __import__("app.application.service", fromlist=["JobCancelled"]).JobCancelled()

    run_batch(store.load(), store, runner, events.append, CancellationToken())
    statuses = {job.display_name: job.status for job in store.load()}
    assert statuses["a.mp4"] == "cancelled"
    assert statuses["b.mp4"] == "pending" and statuses["c.mp4"] == "pending"
    assert any("kept pending" in event for event in events)


def test_run_batch_skips_non_pending_jobs(tmp_path: Path):
    store = BatchStore(tmp_path / "batch_queue.json")
    store.save([make_job("done.mp4", status="completed"), make_job("todo.mp4")])
    ran = []
    run_batch(
        store.load(),
        store,
        lambda job, e, t: ran.append(job.display_name),
        lambda m: None,
        CancellationToken(),
    )
    assert ran == ["todo.mp4"]


def test_batch_job_prompts_roundtrip(tmp_path: Path):
    from app.domain.prompts import PromptSet

    snapshot = dict(PromptSet().to_dict())
    snapshot["summary"] = "BATCH {lang} {transcript}"
    store = BatchStore(tmp_path / "batch_queue.json")
    job = make_job()
    job.prompts = snapshot
    store.save([job])
    loaded = store.load()
    assert loaded[0].prompts is not None
    assert loaded[0].prompt_set() is not None
    assert loaded[0].prompt_set().summary == "BATCH {lang} {transcript}"


def test_batch_job_without_prompts_uses_defaults():
    job = make_job()
    assert job.prompts is None
    assert job.prompt_set() is None
