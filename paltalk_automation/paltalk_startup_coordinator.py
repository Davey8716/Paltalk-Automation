"""Detect Paltalk sessions and coordinate automatic feature startup."""

from PySide6.QtCore import QTimer

from .paltalk_process_worker import PaltalkProcessWorker


class PaltalkStartupCoordinator:
    def __init__(self, window):
        self.window = window
        self.worker = None
        self.timer = QTimer(window)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.check)

    def start(self):
        self.timer.start()
        self.check()

    def check(self):
        if self.worker or self.window._quitting:
            return
        self.worker = PaltalkProcessWorker()
        self.worker.result.connect(self.process_received)
        self.worker.finished.connect(self.process_finished)
        self.worker.start()

    def process_finished(self):
        self.worker = None

    def process_received(self, paltalk_running):
        window = self.window
        if window._quitting:
            return
        if not paltalk_running:
            if window.paltalk_was_running:
                window.log.appendPlainText("Paltalk stopped. Automatic opening is ready for its next session.")
            window.paltalk_was_running = False
            window.room_paltalk_stopped()
            window.camera_auto_handled = False
            return

        if not window.paltalk_was_running:
            window.paltalk_was_running = True
            window.log.appendPlainText("Paltalk detected.")
        if window.camera_auto.isChecked() and not window.camera_auto_handled:
            window.camera_auto_handled = True
            if not window.camera_worker:
                window.start_cameras(automatic=True)
        window.room_paltalk_running()
