"""Keep one application instance per Windows user session."""

import ctypes
from ctypes import wintypes


class SingleInstance:
    def __init__(self, name='Local\\PaltalkAutomationSingleInstance'):
        self._kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self._kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        self._kernel.CreateMutexW.restype = wintypes.HANDLE
        self._kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel.CloseHandle.restype = wintypes.BOOL
        self._handle = self._kernel.CreateMutexW(None, False, name)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.already_running = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS

    def close(self):
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None
