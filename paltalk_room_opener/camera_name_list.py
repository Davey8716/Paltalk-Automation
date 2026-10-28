"""Compact, numbered camera username list."""

# Test data: [f'Test_User_{number:03d}' for number in range(21, 201)]

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QStyledItemDelegate


class CameraNameDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        number = index.data(Qt.ItemDataRole.UserRole)
        if number is not None:
            option.text = f'{number}. {option.text}'


class CameraNameList(QListWidget):
    """Lay out the 200 usernames in six compact, resizable columns."""

    deleteRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setSpacing(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # QListView reserves one grid row at the bottom when wrapping.
        self.setFixedHeight(842)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setGridSize(QSize(max(1, (self.viewport().width() - 16) // 6), 24))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.state() != QAbstractItemView.State.EditingState:
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)
