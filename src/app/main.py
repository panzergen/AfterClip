import faulthandler
import logging
import sys
import threading

import app.app_paths as app_paths
from app.version import version_string

CLI_COMMANDS = frozenset({"run", "batch", "status", "mcp"})


def main(argv: list[str] | None = None) -> int:
    """Dispatch: subcommands run the headless CLI, otherwise launch the GUI."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in CLI_COMMANDS:
        from app.cli import main as cli_main

        return cli_main(args)
    return _run_gui()


def _run_gui() -> int:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QColor, QGuiApplication, QPalette
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
    # Capture otherwise-silent unhandled exceptions (main thread and worker
    # threads) so a post-job crash has a traceback in app.log, not just a
    # vanished window.
    sys.excepthook = lambda exc_type, exc, tb: logging.getLogger("app").error(
        "Unhandled exception", exc_info=(exc_type, exc, tb)
    )

    def _thread_excepthook(*args):
        if len(args) == 1:
            info = args[0]
            exc_type, exc, tb = info.exc_type, info.exc_value, info.exc_traceback
        else:
            exc_type, exc, tb = args[0], args[1], args[2]
        logging.getLogger("app").error(
            "Unhandled exception in worker thread", exc_info=(exc_type, exc, tb)
        )

    threading.excepthook = _thread_excepthook
    # Fatal crashes (native access violations) leave a Python stack trace in
    # crash.log; a windowed launch shows no console, so this is the only
    # place a crash report can be recovered from.
    try:
        faulthandler.enable(file=open(app_paths.crash_file(), "a"), all_threads=True)
    except OSError:
        pass

    QQuickStyle.setStyle("Fusion")
    application = QGuiApplication(sys.argv)
    application.setApplicationName("AfterClip")
    application.setApplicationVersion(version_string())
    # Readable list selection everywhere: the default palette renders the
    # active (highlighted) row with poor contrast in the dropdowns.
    palette = application.palette()
    palette.setColor(QPalette.Highlight, QColor("#0a7bd6"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    application.setPalette(palette)
    # Route Qt/QML warnings/errors into the log so a QML-side crash has a
    # trace (QtCritical/QtFatal at ERROR, warnings at DEBUG).
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def _qt_message(mode, _context, message):
        logger = logging.getLogger("app.qt")
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            logger.error("%s", message)
        elif mode == QtMsgType.QtWarningMsg:
            logger.debug("%s", message)

    qInstallMessageHandler(_qt_message)
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
    context.setContextProperty("presets", controllers.presets)
    context.setContextProperty("voiceprintEnrollment", controllers.voiceprint_enrollment)
    qml_path = app_paths.package_dir() / "ui" / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        return 1
    # Environment checks probe external executables; run them after show().
    QTimer.singleShot(0, controllers.environment.refresh)
    code = application.exec()
    logging.getLogger("app").info("GUI exited (code %s)", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
