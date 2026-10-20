from app.application.highlights import aggregate_highlights, parse_candidates


def candidate(start, title, score):
    return {"start": start, "end": "00:00:00", "title": title, "score": score, "reason": "r"}


def test_parse_candidates_reads_pure_json_array():
    text = (
        '[{"start":"00:01:00","end":"00:01:20","title":"Decision","score":8,"reason":"commitment"}]'
    )
    assert parse_candidates(text) == [
        {
            "start": "00:01:00",
            "end": "00:01:20",
            "title": "Decision",
            "score": 8,
            "reason": "commitment",
        }
    ]


def test_parse_candidates_tolerates_prose_and_fences():
    text = (
        "Here are the highlights:\n"
        "```json\n"
        '[{"start":"00:01:00","end":"00:01:20","title":"Decision","score":8,"reason":"commitment"}]\n'
        "```\n"
        "done."
    )
    parsed = parse_candidates(text)
    assert parsed[0]["title"] == "Decision"


def test_parse_candidates_reads_object_wrapping_list():
    text = '{"highlights":[{"start":"00:01:00","title":"Decision","score":8}]}'
    assert parse_candidates(text)[0]["title"] == "Decision"


def test_parse_candidates_reads_single_object():
    text = '{"start":"00:01:00","end":"00:01:20","title":"Decision","score":8}'
    assert parse_candidates(text)[0]["title"] == "Decision"


def test_parse_candidates_returns_empty_for_non_json():
    assert parse_candidates("no json here at all") == []
    assert parse_candidates("") == []
    assert parse_candidates(None) == []


def test_aggregate_drops_low_scores():
    result = aggregate_highlights(
        [candidate("00:01:00", "keep", 8), candidate("00:02:00", "drop", 6)]
    )
    assert result == "- 00:01:00 keep"


def test_aggregate_deduplicates_near_duplicate_titles():
    result = aggregate_highlights(
        [
            candidate("00:01:00", "Launch date moved to May", 8),
            candidate("00:10:00", "launch date moved to may!", 9),
        ]
    )
    assert result == "- 00:01:00 Launch date moved to May"


def test_aggregate_keeps_one_per_five_minute_window():
    result = aggregate_highlights(
        [
            candidate("00:00:30", "weaker", 7),
            candidate("00:03:00", "stronger same window", 9),
            candidate("00:06:00", "different window", 8),
        ]
    )
    assert "stronger same window" in result
    assert "different window" in result
    assert "weaker" not in result


def test_aggregate_keeps_top_three_sorted_by_score():
    result = aggregate_highlights(
        [
            candidate("00:01:00", "a", 7),
            candidate("00:06:00", "b", 9),
            candidate("00:11:00", "c", 10),
            candidate("00:16:00", "d", 8),
            candidate("00:21:00", "e", 7),
        ]
    )
    lines = result.splitlines()
    assert len(lines) == 3
    assert lines[0] == "- 00:11:00 c"
    assert lines[1] == "- 00:06:00 b"
    assert lines[2] == "- 00:16:00 d"


def test_aggregate_renders_without_timestamp_when_missing():
    result = aggregate_highlights([{"title": "No timestamp", "score": 8}])
    assert result == "- No timestamp"
