from PySide6.QtCore import QObject, Signal, Slot


class PreviewWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, extractor, input_path):
        super().__init__()
        self.extractor = extractor
        self.input_path = input_path

    @Slot()
    def run(self):
        try:
            self.succeeded.emit(self.extractor.extract(self.input_path))
        except Exception as error:
            self.failed.emit(str(error))
