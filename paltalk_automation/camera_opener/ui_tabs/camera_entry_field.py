"""Username entry field for the camera opener."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit


class CameraEntryField(QLineEdit):
    """Show duplicate feedback without replacing the username being typed."""

    def __init__(self):
        super().__init__()
        self.duplicate_message = QLabel('this name has already be been entered', self)
        self.duplicate_message.setStyleSheet('color: #e33b3b; background: transparent; padding: 0;')
        self.duplicate_message.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.duplicate_message.hide()
        self.setMinimumWidth(self.duplicate_message.sizeHint().width() + 150)

    def set_duplicate(self, duplicate):
        if bool(self.property('roomDuplicate')) != duplicate:
            self.setProperty('roomDuplicate', duplicate)
            self.style().unpolish(self)
            self.style().polish(self)
        self.duplicate_message.setVisible(duplicate)
        width = self.duplicate_message.sizeHint().width() if duplicate else 0
        self.setTextMargins(0, 0, width + 12 if duplicate else 0, 0)
        self._position_message()

    def _position_message(self):
        width = self.duplicate_message.sizeHint().width()
        self.duplicate_message.setGeometry(max(0, self.width() - width - 10), 0, width, self.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_message()


