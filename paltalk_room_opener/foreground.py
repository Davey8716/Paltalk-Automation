"""Track the last foreground window outside the Windows notification area."""

import ctypes
import sys
from ctypes import wintypes


class ForegroundTracker:
    SHELL_CLASSES = {'Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'NotifyIconOverflowWindow', 'TopLevelWindowForOverflowXamlIsland'}

    def __init__(self):
        self.last_window = 0
        self._hook = None
        self._callback = None
        if sys.platform != 'win32':
            return
        self._user32 = ctypes.WinDLL('user32', use_last_error=True)
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self._user32.GetAncestor.restype = wintypes.HWND
        self._user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetClassNameW.restype = ctypes.c_int
        callback_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                           wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        self._user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
                                                 callback_type, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        self._user32.SetWinEventHook.restype = wintypes.HANDLE
        self._user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        self._user32.UnhookWinEvent.restype = wintypes.BOOL
        self._callback = callback_type(self._foreground_changed)
        self._hook = self._user32.SetWinEventHook(3, 3, None, self._callback, 0, 0, 0)
        self._remember(self._user32.GetForegroundWindow())

    def _foreground_changed(self, hook, event, hwnd, object_id, child_id, thread_id, event_time):
        self._remember(hwnd)

    def _remember(self, hwnd):
        if not hwnd:
            return
        root = self._user32.GetAncestor(hwnd, 2) or hwnd
        name = ctypes.create_unicode_buffer(256)
        self._user32.GetClassNameW(root, name, len(name))
        if name.value not in self.SHELL_CLASSES:
            self.last_window = int(root)

    def is_foreground(self, window):
        if sys.platform != 'win32' or not self._hook:
            return window.isActiveWindow()
        # Account for a foreground change whose hook notification is still queued.
        self._remember(self._user32.GetForegroundWindow())
        return self.last_window == int(window.winId())

    def close(self):
        if self._hook:
            self._user32.UnhookWinEvent(self._hook)
            self._hook = None
