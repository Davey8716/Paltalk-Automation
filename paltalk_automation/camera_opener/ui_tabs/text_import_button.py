"""Text file import button for the camera opener."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton


class TextImportButton(QPushButton):
    fileDropped = Signal(str)

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _text_file(mime):
        urls = mime.urls() if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() == '.txt' and path.is_file():
                return str(path)
        return None

    def dragEnterEvent(self, event):
        if self._text_file(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._text_file(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.fileDropped.emit(path)
        else:
            event.ignore()


