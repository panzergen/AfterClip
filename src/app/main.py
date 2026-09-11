import faulthandler
import logging
import sys
from pathlib import Path

import app.app_paths as app_paths


def main() -> int:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    from app.infrastructure.logging_filter import SECRET_REDACTOR
    from app.ui.app import build_controllers

    log_path = app_paths.log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.addFilter(SECRET_REDACTOR)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[handler],
    )
    # Fatal crashes (native access violations) leave a Python stack trace in
    # crash.log; a windowed launch shows no console, so this is the only
    # place a crash report can be recovered from.
    try:
        faulthandler.enable(file=open(log_path.parent / "crash.log", "a"), all_threads=True)
    except OSError:
        pass

    QQuickStyle.setStyle("Fusion")
    application = QGuiApplication(sys.argv)
    application.setApplicationName("AfterClip")
    controllers = build_controllers()

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
    qml_path = Path(__file__).resolve().parent / "ui" / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        return 1
    # Environment checks probe external executables; run them after show().
    QTimer.singleShot(0, controllers.environment.refresh)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
