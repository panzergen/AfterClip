from itertools import pairwise

from app.application.topics import (
    TopicSegment,
    render_topics_markdown,
    render_topics_summary,
    segment_topics_cohesion,
    write_topics,
)
from app.domain.models import TimelineEntry


def entry(start_ms, end_ms, text):
    return TimelineEntry(start_ms, end_ms, "00:00:00,000", "00:00:01,000", "TRANSCRIPTION", text)


def test_empty_returns_no_topics():
    assert segment_topics_cohesion(()) == []


def test_single_entry_is_one_section():
    topics = segment_topics_cohesion((entry(0, 1000, "hello world"),))
    assert len(topics) == 1
    assert topics[0].start_ms == 0 and topics[0].end_ms == 1000


def test_boundaries_split_on_topic_change_and_are_monotonic():
    entries = (
        entry(0, 60_000, "project budget planning numbers forecast"),
        entry(60_000, 120_000, "budget forecast planning numbers review"),
        entry(120_000, 180_000, "deployment kubernetes cluster container service"),
        entry(180_000, 240_000, "kubernetes cluster deployment container scaling"),
        entry(240_000, 300_000, "kubernetes container deployment service mesh"),
    )
    topics = segment_topics_cohesion(entries, min_seconds=60, max_sections=5)
    assert len(topics) >= 2
    for first, second in pairwise(topics):
        assert first.end_ms == second.start_ms  # contiguous, non-overlapping
        assert first.start_ms < first.end_ms <= second.end_ms
    assert topics[0].start_ms == 0
    assert topics[-1].end_ms == 300_000


def test_min_seconds_prevents_short_sections():
    entries = tuple(
        entry(index * 10_000, (index + 1) * 10_000, f"topic{index % 2} unique{index}")
        for index in range(12)
    )
    topics = segment_topics_cohesion(entries, min_seconds=120, max_sections=10)
    if len(topics) > 1:
        for topic in topics:
            assert (topic.end_ms - topic.start_ms) >= 120_000


def test_max_sections_caps_output():
    entries = tuple(
        entry(index * 300_000, (index + 1) * 300_000, f"distinct{index} words here")
        for index in range(10)
    )
    topics = segment_topics_cohesion(entries, min_seconds=60, max_sections=3)
    assert len(topics) <= 3


def test_render_and_write_topics(tmp_path):
    topics = [TopicSegment(0, 1000, "00:00:00,000", "00:00:01,000", "Intro")]
    markdown = render_topics_markdown(topics)
    assert "# Topics" in markdown and "Intro" in markdown
    assert render_topics_summary(topics).startswith("- `[00:00:00,000")
    write_topics(tmp_path, topics)
    assert (tmp_path / "Topics.md").is_file()
    assert (tmp_path / "Topics.json").is_file()
