"""Background chat reader worker."""

import json
import subprocess
import time
from PySide6.QtCore import QThread, Signal
from paltalk_automation.helper_process import helper_command, PROJECT_ROOT
from paltalk_automation.settings import load_admin_phrases
from .chat_reader import ChatMessage, ChatSnapshot
from .chat_matches import ChatMatchTracker


class ChatReaderWorker(QThread):
    message = Signal(str)
    match = Signal(str)

    def __init__(self, phrases):
        super().__init__()
        self.tracker = ChatMatchTracker(phrases)

    def read_snapshot(self):
        process = subprocess.Popen(
            helper_command('chat_reader_process'),
            cwd=str(PROJECT_ROOT),
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


