"""Paltalk tracking and overlay lifecycle."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from .layout import scaled_advert_rect
from .overlay import AdvertOverlay
from .windows import WindowEventHook, find_paltalk_window


class PaltalkTracker(QObject):
    _window_event = Signal()

    def __init__(self, overlay: AdvertOverlay, interval_ms: int = 250) -> None:
        super().__init__()
        self._overlay = overlay
        self._enabled = True
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._window_event.connect(self.refresh)
        self._hook = WindowEventHook(self._on_window_event)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        self._timer.start()
        self._hook.start()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()
        self._hook.stop()
        self._overlay.hide()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.refresh()

    def _on_window_event(self) -> None:
        self._window_event.emit()

    def refresh(self) -> None:
        if not self._enabled:
            self._overlay.hide()
            return
        window = find_paltalk_window()
        if window is None:
            self._overlay.hide()
            return
        self._overlay.show_rect(scaled_advert_rect(window.rect), window.hwnd)
