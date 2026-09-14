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


def test_main_qml_defines_primary_keyboard_shortcuts():
    text = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert "StandardKey.Open" in text
    for sequence in ("Ctrl+,", "Ctrl+Return", "Ctrl+.", "Ctrl+1", "Ctrl+4"):
        assert f'sequence: "{sequence}"' in text, f"missing shortcut {sequence}"


def _build_controllers(monkeypatch, tmp_path):
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
    return build_controllers(
        project_dir=tmp_path,
        output_dir=tmp_path / "out",
        batch_store_path=tmp_path / "out" / "batch_queue.json",
        history_output_dir=tmp_path / "out",
        log_path=tmp_path / "out" / "app.log",
    )


def _set_context(context, controllers):
    context.setContextProperty("session", controllers.session)
    context.setContextProperty("media", controllers.media)
    context.setContextProperty("record", controllers.record)
    context.setContextProperty("batch", controllers.batch)
    context.setContextProperty("history", controllers.history)
    context.setContextProperty("env", controllers.environment)
    context.setContextProperty("jobForm", controllers.job_form)
    context.setContextProperty("settings", controllers.settings)


def test_main_qml_loads(qapp, monkeypatch, tmp_path):
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    controllers = _build_controllers(monkeypatch, tmp_path)

    QQuickStyle.setStyle("Fusion")
    engine = QQmlApplicationEngine()
    _set_context(engine.rootContext(), controllers)
    qml_path = Path("src/app/ui/qml/Main.qml").resolve()
    engine.load(qml_path)
    try:
        assert engine.rootObjects(), f"Main.qml failed to load: {qml_path}"
    finally:
        for root in engine.rootObjects():
            root.close()
        engine.deleteLater()


def test_settings_dialog_loads(qapp, monkeypatch, tmp_path):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    controllers = _build_controllers(monkeypatch, tmp_path)

    QQuickStyle.setStyle("Fusion")
    engine = QQmlEngine()
    _set_context(engine.rootContext(), controllers)
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(QML_DIR / "SettingsDialog.qml"))
    )
    dialog = component.create(engine.rootContext())
    try:
        assert component.errors() == [], [error.toString() for error in component.errors()]
        assert dialog is not None
    finally:
        if dialog is not None:
            dialog.deleteLater()
        engine.deleteLater()


def test_settings_dialog_footer_does_not_overlap_content(qapp, monkeypatch, tmp_path):
    """Regression: growing the Gemini group pushed the OK/Cancel footer over it."""
    from PySide6.QtCore import QCoreApplication, QObject
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    controllers = _build_controllers(monkeypatch, tmp_path)

    QQuickStyle.setStyle("Fusion")
    engine = QQmlApplicationEngine()
    _set_context(engine.rootContext(), controllers)
    engine.load(Path("src/app/ui/qml/Main.qml").resolve())
    roots = engine.rootObjects()
    assert roots
    window = roots[0]
    window.resize(1180, 720)
    window.setProperty("settingsOpen", True)
    for _ in range(10):
        QCoreApplication.processEvents()

    dialog = window.findChild(QObject, "settingsDialog")
    try:
        assert dialog is not None
        content = dialog.property("contentItem")
        footer = dialog.property("footer")
        assert content is not None and footer is not None
        content_bottom = content.property("y") + content.property("height")
        assert footer.property("y") >= content_bottom, "settings footer overlaps content"
    finally:
        for root in roots:
            root.close()
        engine.deleteLater()

