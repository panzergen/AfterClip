"""Smoke test: Main.qml loads against the controller layer without QML errors."""

from pathlib import Path

import pytest

from app.infrastructure.settings import InMemorySettingsStore

pytestmark = pytest.mark.ui

QML_DIR = Path(__file__).resolve().parents[2] / "src" / "app" / "ui" / "qml"

# Property names that do not exist on the Qt 6 types they are used on; they
# fail only at runtime with a ReferenceError (e.g. FileDialog uses
# `selectedFiles`, not `selectedUrls`), so a load-time smoke test misses them.
FORBIDDEN_QML_IDENTIFIERS = ("selectedUrls", "selectedFileUrl")


def test_qml_does_not_reference_removed_dialog_properties():
    offenders = [
        path.name
        for path in QML_DIR.rglob("*.qml")
        if any(name in path.read_text(encoding="utf-8") for name in FORBIDDEN_QML_IDENTIFIERS)
    ]
    assert not offenders, f"Use selectedFile/selectedFiles/selectedFolder instead: {offenders}"


def test_multi_file_dialogs_use_selected_files():
    offenders = []
    for path in QML_DIR.rglob("*.qml"):
        text = path.read_text(encoding="utf-8")
        if "FileDialog.OpenFiles" in text and "onAccepted" in text and "selectedFiles" not in text:
            offenders.append(path.name)
    assert not offenders, f"OpenFiles dialogs must consume selectedFiles: {offenders}"


def test_main_qml_loads(qapp, monkeypatch, tmp_path):
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    from app.ui.app import build_controllers

    class NoKeyStore:
        def get(self, name):
            return None

        def set(self, name, value):
            pass

        def delete(self, name):
            pass

    monkeypatch.setattr(
        "app.ui.controllers.environment_controller.check_ollama_service",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr("app.ui.controllers.session_controller.KeyringSecretStore", NoKeyStore)
    monkeypatch.setattr(
        "app.ui.controllers.job_form_controller.JsonSettingsStore",
        lambda: InMemorySettingsStore(),
    )
    monkeypatch.setattr(
        "app.ui.controllers.settings_controller.JsonSettingsStore",
        lambda: InMemorySettingsStore(),
    )
    monkeypatch.setattr("app.ui.controllers.settings_controller.KeyringSecretStore", NoKeyStore)
    controllers = build_controllers(
        project_dir=tmp_path,
        output_dir=tmp_path / "out",
        batch_store_path=tmp_path / "out" / "batch_queue.json",
        history_output_dir=tmp_path / "out",
        log_path=tmp_path / "out" / "app.log",
    )

    QQuickStyle.setStyle("Fusion")
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty("session", controllers.session)
    context.setContextProperty("media", controllers.media)
    context.setContextProperty("record", controllers.record)
    context.setContextProperty("batch", controllers.batch)
    context.setContextProperty("history", controllers.history)
    context.setContextProperty("env", controllers.environment)
    context.setContextProperty("jobForm", controllers.job_form)
    context.setContextProperty("settings", controllers.settings)
    qml_path = Path("src/app/ui/qml/Main.qml").resolve()
    engine.load(qml_path)
    try:
        assert engine.rootObjects(), f"Main.qml failed to load: {qml_path}"
    finally:
        for root in engine.rootObjects():
            root.close()
        engine.deleteLater()
