"""Background worker for room opening."""

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QThread, Signal

from .automation import close_room, navigate_my_rooms, open_rooms, room_states, restore_paltalk, is_paltalk_running
from .chat_reader import ChatMessage, ChatSnapshot
from .chat_matches import ChatMatchTracker
from .settings import load_admin_phrases
from .mic_timer import MicTimeTracker


def helper_command(module, *args):
    """Launch helper modules through the bundled entry point when frozen."""
    executable = sys.executable
    if getattr(sys, 'frozen', False):
        return [executable, '--helper', module, *args]
    if Path(executable).name.lower() == 'pythonw.exe':
        executable = str(Path(executable).with_name('python.exe'))
    return [executable, '-m', f'paltalk_room_opener.{module}', *args]


def run_room_helper(action, names, interrupted, message=None, timeout=20, delay=5):
    """Run a bounded room operation without loading UI Automation in this process."""
    process = subprocess.Popen(
        helper_command('room_helper_process', action, json.dumps(names, ensure_ascii=True), str(delay)),
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
            helper_command('chat_reader_process'),
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


class MicTimerWorker(QThread):
    message = Signal(str)
    room_message = Signal(object, str)

    def __init__(self):
        super().__init__()
        self.tracker = MicTimeTracker()

    def handle_scan(self, data, now):
        if 'error' in data:
            raise RuntimeError(data['error'])
        room = tuple(data['room'])
        speaker = data['speaker']
        if not room or not isinstance(speaker, str):
            raise ValueError('The room scan returned invalid data.')
        previous_room = self.tracker.room
        messages = self.tracker.observe(room, speaker, now)
        for message in messages:
            target = previous_room if message.startswith('Mic timer: room changed;') else room
            self.room_message.emit(target, message)
        state = self.tracker.rooms[room]
        if previous_room is not None and previous_room != room and not messages:
            status = 'Room changed; waiting to confirm the speaker in the newly visible room.'
        elif self.tracker.candidate == speaker.casefold() and (state['name'] or '').casefold() == speaker.casefold():
            status = f'Monitoring: {speaker} is on mic.' if speaker else 'Monitoring: no one is on mic.'
        else:
            status = f'Waiting to confirm speaker: {speaker}.' if speaker else 'Waiting to confirm an empty mic.'
        self.message.emit(status)

    def report_scan_error(self, error):
        self.tracker.pause()
        self.message.emit(f'Mic timer: {error} Waiting for a readable room.')

    def run(self):
        last_error = None
        while not self.isInterruptionRequested():
            if last_error is None:
                self.message.emit('Scanning the visible room…')
            try:
                process = subprocess.Popen(
                    helper_command('mic_timer'),
                    cwd=str(Path(__file__).resolve().parent.parent), stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError as exc:
                self.message.emit(f'Mic timer: could not start room scan: {exc}')
                return
            deadline = time.monotonic() + 25
            try:
                while not self.isInterruptionRequested():
                    try:
                        output, _ = process.communicate(timeout=.2)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Room scan timed out.')
                else:
                    return
                data = json.loads(output.decode('utf-8'))
                self.handle_scan(data, time.monotonic())
                last_error = None
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                message = str(exc)
                if message != last_error:
                    self.report_scan_error(message)
                    last_error = message
                else:
                    self.tracker.pause()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            for _ in range(30):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)


class CameraWorker(QThread):
    message = Signal(str)
    invoked = Signal(str)
    failed = Signal(str)
    live_status = Signal(object)
    manual_opened = Signal(str)

    def __init__(self, names, portrait_adjustment=True, manual_prompt=False):
        super().__init__()
        self.names = list(names)
        self.portrait_adjustment = portrait_adjustment
        self.manual_prompt = manual_prompt
        self.names_lock = threading.Lock()
        self.name_updates = queue.Queue()

    def update_names(self, names):
        with self.names_lock:
            self.names = list(names)
            self.name_updates.put(list(self.names))

    def update_portrait_adjustment(self, enabled):
        with self.names_lock:
            self.portrait_adjustment = bool(enabled)
            self.name_updates.put({'portrait_adjustment': self.portrait_adjustment})

    def update_manual_prompt(self, enabled):
        with self.names_lock:
            self.manual_prompt = bool(enabled)
            self.name_updates.put({'manual_prompt': self.manual_prompt})

    def run(self):
        while not self.isInterruptionRequested():
            try:
                self.run_helper()
            except Exception as exc:
                if not self.isInterruptionRequested():
                    self.live_status.emit([])
                    self.message.emit(f'Camera watcher: {exc} Restarting monitoring shortly.')
            for _ in range(20):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)

    def run_helper(self, timeout=60):
        with self.names_lock:
            initial_names = list(self.names)
            initial_adjustment = self.portrait_adjustment
            initial_manual_prompt = self.manual_prompt
            while not self.name_updates.empty():
                self.name_updates.get_nowait()
        process = subprocess.Popen(
            helper_command('camera_helper_process', json.dumps(initial_names, ensure_ascii=True),
                           json.dumps(initial_adjustment), json.dumps(initial_manual_prompt)),
            cwd=str(Path(__file__).resolve().parent.parent), stdin=subprocess.PIPE,
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
        stage = 'starting camera helper'
        deadline = time.monotonic() + timeout
        try:
            while not self.isInterruptionRequested():
                try:
                    while True:
                        updated = self.name_updates.get_nowait()
                        process.stdin.write((json.dumps(updated, ensure_ascii=True) + '\n').encode('utf-8'))
                        process.stdin.flush()
                except queue.Empty:
                    pass
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    detail = (' The camera outcome is unknown; its visible state will be checked before retrying.'
                              if stage == 'opening a camera' else '')
                    raise RuntimeError(f'Timed out while {stage}.{detail}')
                try:
                    line = events.get(timeout=min(0.2, remaining))
                except queue.Empty:
                    continue
                if line is None:
                    detail = (' The camera outcome is unknown; its visible state will be checked before retrying.'
                              if stage == 'opening a camera' else '')
                    raise RuntimeError(f'Camera helper exited while {stage}.{detail}')
                try:
                    event = json.loads(line.decode('utf-8'))
                    kind, value = event['kind'], event['value']
                    if kind == 'live_status':
                        if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
                            raise ValueError('invalid live status')
                    elif not isinstance(value, str):
                        raise ValueError('invalid event value')
                except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                    raise RuntimeError('Invalid response from camera helper.') from exc
                if kind == 'progress':
                    stage = value
                    deadline = time.monotonic() + timeout
                elif kind == 'message':
                    self.message.emit(value)
                elif kind == 'invoked':
                    self.invoked.emit(value)
                elif kind == 'failed':
                    self.failed.emit(value)
                elif kind == 'live_status':
                    self.live_status.emit(value)
                elif kind == 'manual_opened':
                    self.manual_opened.emit(value)
                elif kind == 'error':
                    raise RuntimeError(value)
        finally:
            # OCR is a child of the helper; terminate it before its parent so it
            # cannot survive a stalled scan or a forced stop.
            try:
                parent = psutil.Process(process.pid)
                parent.suspend()
                children = parent.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                children = []
            for child in reversed(children):
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            if process.poll() is None:
                process.kill()
            process.wait()
            psutil.wait_procs(children, timeout=2)
            process.stdin.close()
            process.stdout.close()
