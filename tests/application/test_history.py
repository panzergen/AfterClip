import json
from pathlib import Path

from app.application.history import read_log_tail, scan_job_history


def test_scan_job_history_finds_jobs_newest_first(tmp_path: Path):
    for name, status in (("job_old", "Succeeded"), ("job_new", "Failed")):
        job_dir = tmp_path / name
        job_dir.mkdir()
        (job_dir / "job_state.json").write_text(
            json.dumps({"status": status, "input_path": f"x/{name}.mp4"}), encoding="utf-8"
        )
    # make job_old older than job_new
    import os
    import time

    os.utime(tmp_path / "job_old" / "job_state.json", (time.time() - 100, time.time() - 100))
    entries = scan_job_history(tmp_path)
    assert [entry.name for entry in entries] == ["job_new", "job_old"]
    assert entries[0].status == "Failed"
    assert entries[0].input_path == "x/job_new.mp4"


def test_scan_job_history_skips_corrupt_state(tmp_path: Path):
    bad = tmp_path / "bad_job"
    bad.mkdir()
    (bad / "job_state.json").write_text("{not json", encoding="utf-8")
    assert scan_job_history(tmp_path) == []


def test_read_log_tail_returns_last_lines(tmp_path: Path):
    log = tmp_path / "app.log"
    log.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    tail = read_log_tail(log, lines=10)
    assert tail.startswith("line 490")
    assert tail.endswith("line 499")
    assert read_log_tail(tmp_path / "missing.log") == "(log file not found)"
