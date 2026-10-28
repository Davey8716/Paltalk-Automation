"""Background worker for room opening."""

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .automation import close_room, open_rooms, room_states, recently_visited_rooms, restore_paltalk, is_paltalk_running
from .camera_automation import watch_cameras
from .chat_reader import ChatMessage, ChatSnapshot
from .chat_matches import ChatMatchTracker
from .settings import load_admin_phrases


def run_room_helper(action, names, interrupted, message=None, timeout=20):
    """Run a bounded room operation without loading UI Automation in this process."""
    executable = sys.executable
    if Path(executable).name.lower() == 'pythonw.exe':
        executable = str(Path(executable).with_name('python.exe'))
    process = subprocess.Popen(
        [executable, '-m', 'paltalk_room_opener.room_helper_process', action, json.dumps(names, ensure_ascii=True)],
        cwd=str(Path(__file__).resolve().parent.parent), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    events = queue.Queue()

    def read_output():
        try:
            for line in process.stdout:
                events.put(line)
        finally:
            events.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    stage = 'starting helper'
    deadline = time.monotonic() + timeout
    try:
        while True:
            if interrupted():
                suffix = ' The room outcome is unknown; check Paltalk before trying again.' if action == 'single' else ''
                raise RuntimeError(f'Room operation stopped during {stage}.{suffix}')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                suffix = ' The room outcome is unknown; check Paltalk before trying again.' if action == 'single' and stage in ('finding room tile', 'invoking room tile') else ''
                raise RuntimeError(f'Room operation timed out during {stage}.{suffix}')
            try:
                line = events.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if line is None:
                suffix = ' The room outcome is unknown; check Paltalk before trying again.' if stage == 'invoking room tile' else ''
                raise RuntimeError(f'Room helper exited during {stage} without a result.{suffix}')
            try:
                event = json.loads(line.decode('utf-8'))
                kind, value = event['kind'], event['value']
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                raise RuntimeError(f'Invalid response from room helper during {stage}.') from exc
            if kind == 'stage':
                stage = value
                deadline = time.monotonic() + timeout
                if message:
                    message(f'Room operation: {stage}...')
            elif kind == 'message' and message:
                message(value)
            elif kind == 'error':
                raise RuntimeError(value)
            elif kind == 'result':
                return value
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


class PaltalkProcessWorker(QThread):
    result = Signal(bool)

    def run(self):
        try:
            self.result.emit(is_paltalk_running())
        except Exception:
            # A failed scan should not be mistaken for Paltalk stopping.
            pass


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

    def __init__(self, names, delay, automatic=False, check_existing=False):
        super().__init__()
        self.names = names
        self.delay = delay
        self.automatic = automatic
        self.check_existing = check_existing

    def run(self):
        if self.check_existing and not self.automatic:
            try:
                result = run_room_helper('single', self.names, self.isInterruptionRequested, self.message.emit)
                self.completed.emit(result)
            except Exception as exc:
                self.message.emit(f'Could not open room: {exc}')
                self.completed.emit(-1)
            return
        try:
            restore_paltalk()
        except Exception as exc:
            self.message.emit(f"Could not restore Paltalk: {exc}")
            self.completed.emit(self.STATE_UNAVAILABLE if self.automatic else -1)
            return
        try:
            names = self.names
            if self.automatic or self.check_existing:
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
        try:
            restore_paltalk()
            states = room_states(self.names)
            if states is None or any(name not in states for name in self.names):
                self.message.emit('Could not determine open room status after restoring Paltalk.')
                return
        except Exception as exc:
            self.message.emit(f'Could not restore Paltalk or check rooms: {exc}')
            return
        for name in self.names:
            if not states[name]:
                continue
            try:
                close_room(name, self.message.emit)
            except Exception as exc:
                self.message.emit(f"Could not close room: {name}. {exc}")


class RoomStateWorker(QThread):
    result = Signal(object)
    message = Signal(str)

    def __init__(self, names):
        super().__init__()
        self.names = names

    def run(self):
        try:
            result = run_room_helper('states', self.names, self.isInterruptionRequested, timeout=10)
            if not self.isInterruptionRequested():
                self.result.emit(result)
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            self.message.emit(f'Could not refresh room status: {exc}')
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
