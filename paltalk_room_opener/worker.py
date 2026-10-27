"""Background worker for room opening."""

from PySide6.QtCore import QThread, Signal

from .automation import open_rooms
from .camera_automation import watch_cameras


class RoomWorker(QThread):
    message = Signal(str)
    completed = Signal(int)

    def __init__(self, names, delay):
        super().__init__()
        self.names = names
        self.delay = delay

    def run(self):
        try:
            queued_rooms = open_rooms(self.names, self.delay, self.message.emit, self.isInterruptionRequested)
            self.completed.emit(queued_rooms)
        except Exception as exc:
            self.message.emit(f"Error: {exc}")
            self.completed.emit(-1)


class CameraWorker(QThread):
    message = Signal(str)

    def __init__(self, names):
        super().__init__()
        self.names = names

    def run(self):
        try:
            watch_cameras(self.names, self.message.emit, self.isInterruptionRequested)
        except Exception as exc:
            self.message.emit(f'Camera watcher error: {exc}')
