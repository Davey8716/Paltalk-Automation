"""Coordinate application shutdown across feature workers."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


class ShutdownCoordinator:
    def __init__(self, window):
        self.window = window

    def _workers(self):
        window = self.window
        return (
            (window.mic_timer_tab.mic_timer_worker, True),
            (window.admin_actions_tab.chat_reader_worker, True),
            (window.camera_worker, True),
            (window.worker, True),
            (window.close_room_worker, False),
            (window.room_state_worker, False),
            (window.recent_rooms_worker, True),
            (window.paltalk_startup.worker, False),
        )

    def close_event(self, event):
        window = self.window
        if not window._quitting and window.tray_icon is not None:
            window.hide()
            event.ignore()
            return
        window.advert_blocker_tab.advert_tracker.stop()
        window.camera_prompts.clear()
        window.camera_restart_pending = False
        window.auto_open_pending = False
        running = False
        for worker, interrupt in self._workers():
            if worker and worker.isRunning():
                if interrupt:
                    worker.requestInterruption()
                running = True
        if running:
            event.ignore()
            if not window._closing_pending:
                window._closing_pending = True
                window.camera_start.setEnabled(False)
                window.start_button.setEnabled(False)
                window.camera_log.appendPlainText('Stopping background work before closing...')
                QTimer.singleShot(100, self.finish_when_stopped)
            return
        window.foreground_tracker.close()
        if window.tray_icon is not None:
            window.tray_icon.hide()
        event.accept()
        if window._quitting:
            QTimer.singleShot(0, QApplication.quit)

    def finish_when_stopped(self):
        if any(worker and worker.isRunning() for worker, _ in self._workers()):
            QTimer.singleShot(100, self.finish_when_stopped)
        else:
            self.window.close()
