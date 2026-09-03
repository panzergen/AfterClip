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
            frames = self.extractor.extract(self.input_path)
            self.succeeded.emit({"frames": frames, "metadata": self.extractor.last_metadata})
        except Exception as error:
            self.failed.emit(str(error))
