import logging
from pathlib import Path


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    logging.basicConfig(
        filename=Path(__file__).resolve().parents[2] / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    application = QApplication([])
    application.setApplicationName("AfterClip")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
