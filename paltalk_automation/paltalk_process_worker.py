"""Background detection of the Paltalk process."""

from PySide6.QtCore import QThread, Signal
from paltalk_automation.room_opener.backend.automation import is_paltalk_running


class PaltalkProcessWorker(QThread):
    result = Signal(bool)

    def run(self):
        try:
            self.result.emit(is_paltalk_running())
        except Exception:
            # A failed scan should not be mistaken for Paltalk stopping.
            pass


