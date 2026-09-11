import pytest

from app.application.cloud_usage import estimate_cost_usd
from app.application.service_io import write_report
from app.domain.models import CloudUsage, TranscriptionRequest


def test_estimate_cost_known_model():
    usage = CloudUsage(
        provider="gemini",
        model="gemini-2.5-flash",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert estimate_cost_usd(usage) == pytest.approx(2.80)


def test_estimate_cost_unknown_model_is_none():
    usage = CloudUsage(provider="gemini", model="some-future-model", input_tokens=1000)
    assert estimate_cost_usd(usage) is None


def test_merged_sums_counters():
    first = CloudUsage(provider="gemini", model="m", requests=1, input_tokens=10, images=1)
    second = CloudUsage(provider="gemini", model="m", requests=2, output_tokens=5)
    merged = first.merged(second)
    assert merged.requests == 3
    assert merged.input_tokens == 10
    assert merged.output_tokens == 5
    assert merged.images == 1
    assert merged.provider == "gemini"
    assert merged.model == "m"


def test_report_includes_cloud_usage(tmp_path):
    request = TranscriptionRequest(tmp_path / "in.mp4", tmp_path / "out")
    report = tmp_path / "Summary_Report.md"
    metadata = {
        "cloud_usage": {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "requests": 3,
            "input_tokens": 100,
            "output_tokens": 50,
            "images": 2,
            "estimated_cost_usd": 0.000145,
            "cost_note": "Approximate",
        }
    }
    write_report(report, request, "Succeeded", metadata, {})
    text = report.read_text(encoding="utf-8")
    assert "## Cloud Usage (approximate)" in text
    assert "**Images sent:** `2`" in text
    assert "$0.000145" in text


def test_report_omits_usage_section_without_usage(tmp_path):
    request = TranscriptionRequest(tmp_path / "in.mp4", tmp_path / "out")
    report = tmp_path / "Summary_Report.md"
    write_report(report, request, "Succeeded", {}, {})
    assert "Cloud Usage" not in report.read_text(encoding="utf-8")
