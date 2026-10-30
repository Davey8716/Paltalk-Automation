"""Background mic timer worker."""

import json
import subprocess
import time
from PySide6.QtCore import QThread, Signal
from paltalk_automation.helper_process import helper_command, PROJECT_ROOT
from .mic_timer import MicTimeTracker


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
                    cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE,
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


