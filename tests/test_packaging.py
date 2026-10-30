import re
import sys
import tomllib
from pathlib import Path

import app.app_paths as app_paths
from app.version import __version__, version_info_version, version_string

ROOT = Path(__file__).resolve().parents[1]


def test_version_is_semver_like():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_version_string_matches_module_version():
    assert version_string() == __version__


def test_version_info_version_is_a_numeric_quad():
    """The version used for Windows resources: exactly four numeric parts."""
    info_version = version_info_version()
    parts = info_version.split(".")
    assert len(parts) == 4
    assert info_version.startswith(__version__)
    assert all(part.isdigit() for part in parts)


def test_pyproject_reads_version_from_code():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]
    attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "app.version.__version__"


def test_package_dir_points_at_source_for_checkout_runs(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    package = app_paths.package_dir()
    assert package.name == "app"
    assert (package / "ui" / "qml" / "Main.qml").is_file()


def test_is_frozen_defaults_false(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert app_paths.is_frozen() is False


def test_frozen_bundle_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("AFTERCLIP_HOME", raising=False)
    assert app_paths.is_frozen() is True
    assert app_paths.bundle_dir() == tmp_path
    assert app_paths.package_dir() == tmp_path / "app"
    assert app_paths.project_dir() == app_paths.default_workspace_dir()


def test_afterclip_home_overrides_frozen_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path / "home"))
    assert app_paths.project_dir() == (tmp_path / "home").resolve()


def test_app_data_dir_honours_localappdata(monkeypatch, tmp_path):
    # Pin the platform: LOCALAPPDATA is only consulted on Windows, and the
    # test asserts the Windows layout.
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert app_paths.app_data_dir() == tmp_path / "AfterClip"
    assert app_paths.log_file() == tmp_path / "AfterClip" / "logs" / "app.log"
    assert app_paths.crash_file() == tmp_path / "AfterClip" / "logs" / "crash.log"


def test_app_data_dir_honours_xdg_data_home(monkeypatch, tmp_path):
    """The POSIX layout, which the Windows test above does not cover."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert app_paths.app_data_dir() == tmp_path / "AfterClip"


def test_app_data_dir_uses_application_support_on_macos(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert app_paths.app_data_dir() == tmp_path / "Library" / "Application Support" / "AfterClip"


def test_packaging_assets_present():
    assert (ROOT / "packaging" / "entry_point.py").is_file()
    assert (ROOT / "packaging" / "build_windows.ps1").is_file()
    spec = (ROOT / "packaging" / "AfterClip.spec").read_text(encoding="utf-8")
    assert "app/ui/qml" in spec
    assert "app.version" in spec
    assert "speakeronnx" in spec
    assert "onnxruntime" in spec
    installer = (ROOT / "packaging" / "afterclip.iss").read_text(encoding="utf-8")
    assert "OutputBaseFilename=AfterClip-{#AppVersion}-setup" in installer
    assert 'SourceDir "..\\release\\AfterClip"' in installer
    assert "VersionInfoVersion={#AppVersionInfoVersion}" in installer
    build_script = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    assert '"/DAppVersionInfoVersion=$versionInfoVersion"' in build_script
    assert '".[build,voiceprint]"' in build_script
