"""Tests for the shared atomic text writer."""

import threading
from pathlib import Path

from app.infrastructure.atomic_file import atomic_write_text


def test_write_creates_parent_directories(tmp_path: Path):
    target = tmp_path / "nested" / "deeper" / "report.md"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_write_leaves_no_temporary_files_behind(tmp_path: Path):
    target = tmp_path / "report.md"
    atomic_write_text(target, "hello")
    assert [p.name for p in tmp_path.iterdir()] == ["report.md"]


def test_concurrent_writers_to_the_same_target_all_succeed(tmp_path: Path):
    """Regression: a fixed temp name let racing writers collide.

    Two writers sharing ``.<name>.tmp`` meant the loser's ``os.replace`` hit
    a file another handle still had open, which Windows reports as
    ``PermissionError``. Each call now uses a unique temp name.
    """
    target = tmp_path / "state.json"
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def writer(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            atomic_write_text(target, f'{{"writer": {index}}}')
        except BaseException as error:  # recorded so the assert below can report it
            errors.append(error)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"concurrent writes failed: {errors}"
    # The target must hold one complete write, never a truncated mix.
    content = target.read_text(encoding="utf-8")
    assert content.startswith('{"writer":') and content.endswith("}")
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_failed_write_does_not_leave_a_temporary_file(tmp_path: Path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text("original", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.infrastructure.atomic_file.os.replace", boom)
    try:
        atomic_write_text(target, "new content")
    except OSError:
        pass
    else:  # pragma: no cover - the failure is the point of the test
        raise AssertionError("expected OSError")

    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]
