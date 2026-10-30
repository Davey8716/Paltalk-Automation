"""Background camera monitoring worker."""

import json
import queue
import subprocess
import threading
import time
import psutil
from PySide6.QtCore import QThread, Signal
from paltalk_automation.helper_process import helper_command, PROJECT_ROOT


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
            cwd=str(PROJECT_ROOT), stdin=subprocess.PIPE,
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
