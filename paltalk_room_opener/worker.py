"""Background worker for room opening."""

from PySide6.QtCore import QThread, Signal

from .automation import close_room, open_rooms, room_states, recently_visited_rooms
from .camera_automation import watch_cameras


class RoomWorker(QThread):
    message = Signal(str)
    completed = Signal(int)
    STATE_UNAVAILABLE = -2
    ALREADY_OPEN = -3

    def __init__(self, names, delay, automatic=False):
        super().__init__()
        self.names = names
        self.delay = delay
        self.automatic = automatic

    def run(self):
        try:
            names = self.names
            if self.automatic:
                try:
                    states = room_states(names)
                except Exception as exc:
                    self.message.emit(f"Could not determine open room status: {exc}")
                    self.completed.emit(self.STATE_UNAVAILABLE)
                    return
                unknown = [name for name in names if states is None or name not in states]
                if unknown:
                    self.message.emit(f"Could not determine open room status: {', '.join(unknown)}.")
                    self.completed.emit(self.STATE_UNAVAILABLE)
                    return
                names = [name for name in names if not states[name]]
                for name in self.names:
                    if states[name]:
                        self.message.emit(f"Already open, skipping room: {name}")
                if not names:
                    self.message.emit("All configured rooms are already open.")
                    self.completed.emit(self.ALREADY_OPEN)
                    return
            queued_rooms = open_rooms(names, self.delay, self.message.emit, self.isInterruptionRequested)
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
