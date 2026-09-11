from app.application.service_io import atomic_write_text, load_state, save_state


def test_save_state_is_atomic_and_readable(tmp_path):
    path = tmp_path / "job_state.json"
    save_state(path, {"status": "running", "steps": {}})
    assert load_state(path)["status"] == "running"
    # No leftover temp files: the replace completed.
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_write_replaces_existing(tmp_path):
    path = tmp_path / "file.txt"
    atomic_write_text(path, "one")
    atomic_write_text(path, "two")
    assert path.read_text(encoding="utf-8") == "two"


def test_atomic_write_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "file.txt"
    atomic_write_text(path, "content")
    assert path.read_text(encoding="utf-8") == "content"
