"""Opaque PySide6 overlay window."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from .layout import Rect


GW_HWNDPREV = 3
HWND_TOP = 0


class AdvertOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet("background: #ffffff;")

    def show_rect(self, rect: Rect, paltalk_hwnd: int) -> None:
        was_hidden = not self.isVisible()
        self.setGeometry(rect.x, rect.y, rect.width, rect.height)
        self.show()
        if was_hidden:
            self.raise_()
        if os.name == "nt":
            self._position_in_paltalk_z_order(rect, paltalk_hwnd)

    def _position_in_paltalk_z_order(self, rect: Rect, paltalk_hwnd: int) -> None:
        """Place the overlay immediately above Paltalk in the Windows Z-order."""
        overlay_hwnd = int(self.winId())
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
        user32.GetWindow.restype = wintypes.HWND
        user32.SetWindowPos.argtypes = (
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        )
        user32.SetWindowPos.restype = wintypes.BOOL
        insert_after = int(user32.GetWindow(paltalk_hwnd, GW_HWNDPREV) or HWND_TOP)
        if insert_after == overlay_hwnd:
            return
        user32.SetWindowPos(
            overlay_hwnd, insert_after,
            rect.x, rect.y, rect.width, rect.height, 0x0010 | 0x0001,
        )
