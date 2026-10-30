"""Background workers for room operations."""

import json
import queue
import subprocess
import threading
import time
from PySide6.QtCore import QThread, Signal
from paltalk_automation.helper_process import helper_command, PROJECT_ROOT
from .automation import close_room, navigate_my_rooms, open_rooms, room_states, restore_paltalk


def run_room_helper(action, names, interrupted, message=None, timeout=20, delay=5):
    """Run a bounded room operation without loading UI Automation in this process."""
    process = subprocess.Popen(
        helper_command('room_helper_process', action, json.dumps(names, ensure_ascii=True), str(delay)),
        cwd=str(PROJECT_ROOT), stdin=subprocess.DEVNULL,
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
                suffix = ' The room outcome is unknown; check Paltalk before trying again.' if action == 'single' and stage in ('finding room tile', 'invoking room tile', 'closing room') else ''
                raise RuntimeError(f'Room operation timed out during {stage}.{suffix}')
            try:
                line = events.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if line is None:
                suffix = ' The room outcome is unknown; check Paltalk before trying again.' if stage in ('invoking room tile', 'closing room') else ''
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
        if self.automatic:
            try:
                result = run_room_helper('automatic', self.names, self.isInterruptionRequested,
                                         self.message.emit, timeout=max(20, self.delay + 20), delay=self.delay)
                self.completed.emit(result)
            except Exception as exc:
                self.message.emit(f'Automatic room opening failed: {exc}')
                self.completed.emit(self.STATE_UNAVAILABLE)
            return
        if self.check_existing and not self.automatic:
            try:
                result = run_room_helper('single', self.names, self.isInterruptionRequested, self.message.emit)
                self.completed.emit(result)
            except Exception as exc:
                self.message.emit(f'Could not toggle room: {exc}')
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
            self.message.emit('Opening Paltalk My Rooms...')
            navigate_my_rooms(self.isInterruptionRequested)
            if self.isInterruptionRequested():
                self.message.emit('Stopped.')
                self.completed.emit(0)
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

    def __init__(self, automatic=False):
        super().__init__()
        self.automatic = automatic

    def run(self):
        try:
            names = run_room_helper('recent_background' if self.automatic else 'recent', [],
                                    self.isInterruptionRequested, timeout=10)
            if not self.isInterruptionRequested():
                self.result.emit(names, "")
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.result.emit([], str(exc))


