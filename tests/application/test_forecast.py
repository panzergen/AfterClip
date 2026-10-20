import json

import pytest

from app.application.forecast import (
    HistoricalJob,
    forecast,
    format_estimate,
    load_history,
)


def _state(
    duration,
    model,
    modes,
    analyze_text=False,
    analyze_vision=False,
    transcription=100,
    forecast=None,
):
    state = {
        "status": "Succeeded",
        "media": {"duration": duration, "file_size_mb": 10},
        "run_settings": {
            "model": model,
            "frame_modes": list(modes),
            "frame_resolution": "full",
            "analyze_text": analyze_text,
            "analyze_vision": analyze_vision,
        },
        "steps": {
            "transcription": {"status": "completed", "duration_seconds": transcription},
            "master_timeline": {"status": "completed", "duration_seconds": 2},
        },
    }
    if forecast is not None:
        state["forecast"] = forecast
    return state


def test_load_history_reads_media_and_settings(tmp_path):
    out = tmp_path / "out"
    (out / "job1").mkdir(parents=True)
    (out / "job1" / "job_state.json").write_text(
        json.dumps(_state(1000, "turbo", ("interval",), analyze_text=True)), encoding="utf-8"
    )
    (out / "empty").mkdir()
    (out / "empty" / "job_state.json").write_text(json.dumps({"steps": {}}), encoding="utf-8")

    jobs = load_history(out)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.duration_seconds == 1000
    assert job.total_seconds == 102
    assert job.model == "turbo"
    assert job.frame_modes == ("interval",)
    assert job.analyze_text is True
    assert job.rate is not None


def test_load_history_handles_missing_directory(tmp_path):
    assert load_history(tmp_path / "nope") == []


def test_load_history_reads_stored_prediction(tmp_path):
    out = tmp_path / "out"
    (out / "job1").mkdir(parents=True)
    state = _state(1000, "turbo", ("interval",), forecast={"expected_seconds": 250.0})
    (out / "job1" / "job_state.json").write_text(json.dumps(state), encoding="utf-8")

    jobs = load_history(out)
    assert jobs[0].predicted_seconds == 250.0


def test_load_history_ignores_missing_or_zero_prediction(tmp_path):
    out = tmp_path / "out"
    (out / "job1").mkdir(parents=True)
    (out / "job1" / "job_state.json").write_text(
        json.dumps(_state(1000, "turbo", ("interval",))), encoding="utf-8"
    )
    (out / "job2").mkdir(parents=True)
    (out / "job2" / "job_state.json").write_text(
        json.dumps(_state(1000, "turbo", ("interval",), forecast={"expected_seconds": 0})),
        encoding="utf-8",
    )

    jobs = load_history(out)
    assert all(job.predicted_seconds is None for job in jobs)


def test_forecast_uses_similar_history_median_rate():
    history = [
        HistoricalJob(1000, 260, "turbo", ("interval",), False, False, "full"),
        HistoricalJob(2000, 500, "turbo", ("interval",), False, False, "full"),
        HistoricalJob(3000, 780, "turbo", ("interval",), False, False, "full"),
        HistoricalJob(1000, 999, "turbo", ("scene",), False, False, "full"),  # different config
    ]
    result = forecast(1000, "turbo", ("interval",), False, False, history=history)
    assert result.available is True
    assert result.basis == "similar"
    assert result.sample_count == 3
    # rates ~0.26/0.25/0.26 -> median ~0.26 * 1000 ≈ 260s
    assert 230 < result.expected_seconds < 290
    assert result.low_seconds <= result.expected_seconds <= result.high_seconds


def test_forecast_relaxes_to_model_then_heuristic():
    model_only = [
        HistoricalJob(1000, 100, "small", (), False, False, "full"),
        HistoricalJob(1000, 100, "small", (), False, False, "full"),
        HistoricalJob(1000, 100, "small", (), False, False, "full"),
    ]
    result = forecast(1000, "small", ("interval",), True, False, history=model_only)
    assert result.basis == "model"
    assert result.sample_count == 3

    heuristic = forecast(600, "turbo", (), False, False, history=[])
    assert heuristic.available is True
    assert heuristic.basis == "heuristic"
    assert heuristic.sample_count == 0
    assert heuristic.expected_seconds == 150  # 600 * 0.25


def _job(predicted_seconds=None):
    return HistoricalJob(
        1000, 200, "turbo", ("interval",), False, False, "full", predicted_seconds=predicted_seconds
    )


def test_forecast_self_corrects_from_stored_predictions():
    history = [_job(100), _job(100), _job(100)]
    result = forecast(1000, "turbo", ("interval",), False, False, history=history)
    # raw rate 0.2 -> 200s; median actual/predicted = 2.0 -> corrected to 400s.
    assert result.expected_seconds == pytest.approx(400.0)
    assert result.low_seconds == pytest.approx(400.0)
    assert result.high_seconds == pytest.approx(400.0)


def test_forecast_ignores_few_predictions():
    history = [_job(100), _job(100), _job()]
    result = forecast(1000, "turbo", ("interval",), False, False, history=history)
    assert result.expected_seconds == pytest.approx(200.0)


def test_forecast_unavailable_without_duration():
    result = forecast(0, "turbo")
    assert result.available is False
    assert result.text() == ""


def test_forecast_text_variants():
    similar = forecast(
        1000,
        "turbo",
        ("interval",),
        False,
        False,
        history=[
            HistoricalJob(1000, 250, "turbo", ("interval",), False, False, "full"),
            HistoricalJob(1000, 250, "turbo", ("interval",), False, False, "full"),
            HistoricalJob(1000, 250, "turbo", ("interval",), False, False, "full"),
        ],
    )
    assert similar.text().startswith("Estimated")
    assert "similar job" in similar.text()

    rough = forecast(600, "turbo")
    assert rough.text().startswith("Rough estimate")


def test_format_estimate_units():
    assert format_estimate(30) == "under 1m"
    assert format_estimate(600) == "~10m"
    assert format_estimate(3600) == "~1h"
    assert format_estimate(3900) == "~1h 05m"
