"""Background worker for room opening."""

import json
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .automation import close_room, open_rooms, room_states, recently_visited_rooms
from .camera_automation import watch_cameras
from .chat_reader import ChatMessage, ChatSnapshot
from .chat_matches import ChatMatchTracker
from .settings import load_admin_phrases


class ChatReaderWorker(QThread):
    message = Signal(str)
    match = Signal(str)

    def __init__(self, phrases):
        super().__init__()
        self.tracker = ChatMatchTracker(phrases)

    def read_snapshot(self):
        process = subprocess.Popen(
            [sys.executable, '-m', 'paltalk_room_opener.chat_reader_process'],
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        deadline = time.monotonic() + 20
        try:
            while not self.isInterruptionRequested():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Windows UI Automation timed out.')
                try:
                    stdout, stderr = process.communicate(timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            else:
                return None
            if process.returncode:
                raise RuntimeError('Chat scan failed: ' + (stderr.decode('utf-8', 'replace').splitlines()[-1] if stderr else 'unknown error'))
            data = json.loads(stdout)
            if 'error' in data:
                raise RuntimeError(data['error'])
            data = data['snapshot']
            messages = tuple(ChatMessage(item['sender'], item['text'], tuple(item['runtime_id']))
                             for item in data['messages'])
            return ChatSnapshot(tuple(data['room_id']), messages,
                                tuple(tuple(item) for item in data['message_ids']))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def run(self):
        room_id = None
        seen = set()
        last_error = None
        while not self.isInterruptionRequested():
            try:
                snapshot = self.read_snapshot()
                if snapshot is None:
                    break
                self.tracker.phrases = tuple(p for p in load_admin_phrases() if p.strip())
                if snapshot.room_id != room_id:
                    room_id = snapshot.room_id
                    seen.clear()
                    self.message.emit('Reading selected room chat.')
                if last_error is not None:
                    self.message.emit('Chat reader recovered and resumed.')
                last_error = None
                for item, phrase in self.tracker.scan(snapshot):
                    self.match.emit(f'Room: name unavailable (ID {snapshot.room_id})\nUser: {item.sender}\nMessage: {item.text}\nPhrase: {phrase}\n')
                for item in snapshot.messages:
                    key = (item.runtime_id, item.sender, item.text)
                    if key not in seen:
                        seen.add(key)
                        self.message.emit(f'{item.sender}: {item.text}')
            except Exception as exc:
                error = str(exc).splitlines()[0].strip() or type(exc).__name__
                if '0x80131505' in error.lower() or 'timed out' in error.lower():
                    error = 'Windows UI Automation timed out. Retrying; some messages may be missed.'
                if error != last_error:
                    self.message.emit(f'Chat reader: {error}')
                    last_error = error
            for _ in range(20):
                if self.isInterruptionRequested():
                    break
                self.msleep(100)


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
