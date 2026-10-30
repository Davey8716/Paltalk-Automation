"""Advert blocker tab and overlay controller."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from . import settings
from paltalk_adblocker.overlay import AdvertOverlay
from paltalk_adblocker.tracker import PaltalkTracker


class AdvertBlockerTab(QWidget):
    def __init__(self, log, parent=None):
        super().__init__(parent)
        self.log = log
        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 24, 38, 32)
        layout.addWidget(QLabel('Cover the advert area in the Paltalk window.'))
        self.advert_toggle = QPushButton('Advert overlay: Off')
        self.advert_toggle.setCheckable(True)
        self.advert_toggle.setMaximumWidth(220)
        layout.addWidget(self.advert_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        self.advert_overlay = AdvertOverlay()
        self.advert_tracker = PaltalkTracker(self.advert_overlay)

    def set_advert_overlay_enabled(self, enabled, save=True):
        self.advert_toggle.setText(f'Advert overlay: {"On" if enabled else "Off"}')
        if enabled:
            self.advert_tracker.set_enabled(True)
            self.advert_tracker.start()
        else:
            self.advert_tracker.stop()
            self.advert_tracker.set_enabled(False)
        if save:
            try:
                settings.save_app_state(advert_overlay_enabled=enabled)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                self.log.appendPlainText(f'Could not save app state: {exc}')

