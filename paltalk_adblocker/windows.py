"""Minimal Win32 integration for Paltalk discovery and monitor geometry."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Callable

from .layout import MonitorGeometry, Rect


if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)


def _configure_win32() -> None:
    if os.name != "nt":
        return
    user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, wintypes.LPDWORD)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(_RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MONITORINFO))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.SetWinEventHook.argtypes = (
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, WINEVENTPROC,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    )
    user32.SetWinEventHook.restype = wintypes.HANDLE
    user32.UnhookWinEvent.argtypes = (wintypes.HANDLE,)
    user32.UnhookWinEvent.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, wintypes.LPDWORD,
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    dwmapi.DwmGetWindowAttribute.argtypes = (
        wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
    )
    dwmapi.DwmGetWindowAttribute.restype = wintypes.LONG


_configure_win32()


@dataclass(frozen=True)
class PaltalkWindow:
    hwnd: int
    rect: Rect


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GW_OWNER = 4
MONITOR_DEFAULTTONEAREST = 2
DWMWA_CLOAKED = 14


def enable_per_monitor_dpi_awareness() -> None:
    """Request physical-pixel coordinates before creating a QApplication."""
    if os.name != "nt":
        return
    # PER_MONITOR_AWARE_V2 is only available on modern Windows 10 builds.
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except AttributeError:
        pass
    try:
        shcore = ctypes.WinDLL("shcore")
        if shcore.SetProcessDpiAwareness(2) == 0:
            return
    except OSError:
        pass
    user32.SetProcessDPIAware()


def _window_rect(hwnd: int) -> Rect | None:
    rect = _RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None
    return Rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def _is_cloaked(hwnd: int) -> bool:
    cloaked = wintypes.DWORD()
    return dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    ) == 0 and bool(cloaked.value)


def _process_name(pid: int) -> str | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            return None
        return PureWindowsPath(path.value).name.lower()
    finally:
        kernel32.CloseHandle(handle)


def find_paltalk_window() -> PaltalkWindow | None:
    """Find the largest visible, unowned Paltalk top-level window."""
    if os.name != "nt":
        return None
    candidates: list[PaltalkWindow] = []
    process_names: dict[int, str | None] = {}

    @WNDENUMPROC
    def callback(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER) or _is_cloaked(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = process_names.setdefault(pid.value, _process_name(pid.value))
        if name != "paltalk.exe":
            return True
        rect = _window_rect(hwnd)
        if rect and rect.width > 0 and rect.height > 0:
            candidates.append(PaltalkWindow(int(hwnd), rect))
        return True

    user32.EnumWindows(callback, 0)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.rect.width * item.rect.height)


def monitor_for_window(hwnd: int) -> MonitorGeometry | None:
    if os.name != "nt":
        return None
    monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
    if not monitor:
        return None
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    rect = info.rcMonitor
    return MonitorGeometry(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


class WindowEventHook:
    """Out-of-context WinEvent hooks, with an ordinary polling fallback elsewhere."""

    EVENT_MIN = 0x0003
    EVENT_MAX = 0x8017
    WINEVENT_OUTOFCONTEXT = 0
    WINEVENT_SKIPOWNPROCESS = 2

    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._hook: int | None = None
        self._proc = None

    def start(self) -> None:
        if os.name != "nt" or self._hook:
            return

        @WINEVENTPROC
        def proc(_: int, __: int, ___: int, ____: int, _____: int, ______: int, _______: int) -> None:
            self._callback()

        self._proc = proc
        self._hook = user32.SetWinEventHook(
            self.EVENT_MIN, self.EVENT_MAX, None, self._proc, 0, 0,
            self.WINEVENT_OUTOFCONTEXT | self.WINEVENT_SKIPOWNPROCESS,
        )

    def stop(self) -> None:
        if self._hook:
            user32.UnhookWinEvent(self._hook)
            self._hook = None
        self._proc = None
