from PySide6.QtCore import QObject, Signal, Slot


class RecorderStopWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    @Slot()
    def run(self):
        try:
            self.succeeded.emit(self.recorder.stop())
        except Exception as error:
            self.failed.emit(str(error))
