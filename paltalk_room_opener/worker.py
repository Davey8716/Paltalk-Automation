"""Background worker for room opening."""

from PySide6.QtCore import QThread, Signal

from .automation import close_room, open_rooms, room_states, recently_visited_rooms
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


class CloseRoomWorker(QThread):
    message = Signal(str)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def run(self):
        try:
            close_room(self.name, self.message.emit)
        except Exception as exc:
            self.message.emit(f"Could not close room: {self.name}. {exc}")


class CloseAllRoomsWorker(QThread):
    message = Signal(str)

    def __init__(self, names):
        super().__init__()
        self.names = names

    def run(self):
        for name in self.names:
            try:
                close_room(name, self.message.emit)
            except Exception as exc:
                self.message.emit(f"Could not close room: {name}. {exc}")


class RoomStateWorker(QThread):
    result = Signal(object)

    def __init__(self, names):
        super().__init__()
        self.names = names

    def run(self):
        try:
            self.result.emit(room_states(self.names))
        except Exception:
            self.result.emit(None)


class RecentRoomsWorker(QThread):
    result = Signal(object, str)

    def run(self):
        try:
            self.result.emit(recently_visited_rooms(), "")
        except Exception as exc:
            self.result.emit([], str(exc))


class CameraWorker(QThread):
    message = Signal(str)
    invoked = Signal(str)
    failed = Signal(str)

    def __init__(self, names):
        super().__init__()
        self.names = names

    def run(self):
        try:
            watch_cameras(self.names, self.message.emit, self.isInterruptionRequested,
                          self.invoked.emit, self.failed.emit)
        except Exception as exc:
            self.message.emit(f'Camera watcher error: {exc}')
