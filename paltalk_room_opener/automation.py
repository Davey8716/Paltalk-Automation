"""Windows UI Automation routines for Paltalk room tiles."""

import os
import ctypes
import subprocess
import time
from ctypes import wintypes
from importlib import import_module
from pathlib import Path

import psutil


def is_paltalk_running():
    """Return whether the main Paltalk desktop client is running."""
    return any(
        (process.info.get("name") or "").lower() == "paltalk.exe"
        for process in psutil.process_iter(["name"])
    )


def recently_visited_rooms():
    """Read room tiles following Paltalk's Recently Visited section header."""
    clr = import_module("clr")
    root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "assembly" / "GAC_MSIL"
    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        paths = sorted((root / assembly).glob(f"*/{assembly}.dll"))
        clr.AddReference(str(paths[-1]) if paths else assembly)
    a = import_module("System.Windows.Automation")
    pids = {p.info["pid"] for p in psutil.process_iter(["pid", "name"])
            if (p.info.get("name") or "").lower() == "paltalk.exe"}
    windows = a.AutomationElement.RootElement.FindAll(a.TreeScope.Children,
        a.PropertyCondition(a.AutomationElement.ControlTypeProperty, a.ControlType.Window))
    for window in windows:
        if window.Current.ProcessId not in pids:
            continue
        button = window.FindFirst(a.TreeScope.Descendants,
            a.PropertyCondition(a.AutomationElement.NameProperty, "BaseButton133"))
        if button is None:
            continue
        walker = a.TreeWalker.ControlViewWalker
        header = walker.GetParent(button)
        if header is None:
            continue
        container = walker.GetParent(header)
        if container is None or header.Current.ClassName != "ui::rooms::ClosableListWidget":
            continue

        def read_tiles():
            children = container.FindAll(a.TreeScope.Children, a.Condition.TrueCondition)
            after_header = False
            names = []
            for child in children:
                if not after_header:
                    after_header = child.Equals(header)
                elif child.Current.ClassName == "ui::rooms::RoomTiles":
                    name = child.Current.Name
                    if name and name not in names:
                        names.append(name)
                else:
                    break
            return names

        names = read_tiles()
        if names:
            return names
        # The list may be collapsed. Restore the original state even if reading fails.
        toggle = button.GetCurrentPattern(a.InvokePattern.Pattern)
        toggle.Invoke()
        try:
            time.sleep(0.5)
            return read_tiles()
        finally:
            toggle.Invoke()
    raise RuntimeError("Recently Visited was not found. Open Paltalk's Rooms view and try again.")


def _paltalk_windows(a):
    pids = {p.info["pid"] for p in psutil.process_iter(["pid", "name"])
            if (p.info.get("name") or "").lower() == "paltalk.exe"}
    if not pids:
        return []
    windows = a.AutomationElement.RootElement.FindAll(
        a.TreeScope.Children, a.PropertyCondition(a.AutomationElement.ControlTypeProperty, a.ControlType.Window))
    return [window for window in windows if window.Current.ProcessId in pids]


class PaltalkWindowNotFound(RuntimeError):
    """The Paltalk main window is unavailable or cannot be selected safely."""

    def __init__(self, message, processes=0, title_matches=0):
        super().__init__(message)
        self.processes = processes
        self.title_matches = title_matches


def _paltalk_main_window(user32):
    """Find the unowned, maximizable Paltalk window, including hidden windows."""
    pids = {p.info['pid'] for p in psutil.process_iter(['pid', 'name'])
            if (p.info.get('name') or '').lower() == 'paltalk.exe'}
    windows = []
    counts = {'top-level': 0, 'unowned': 0, 'maximizable': 0, 'title matches': 0, 'main-class matches': 0}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]

    @callback_type
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        counts['top-level'] += 1
        if user32.GetWindow(hwnd, 4):  # GW_OWNER
            return True
        counts['unowned'] += 1
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        if not style & 0x00010000:  # WS_MAXIMIZEBOX
            return True
        counts['maximizable'] += 1
        title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        if title.value.strip().casefold() == 'paltalk':
            counts['title matches'] += 1
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            windows.append((hwnd, class_name.value))
            if class_name.value.startswith('Qt') and class_name.value.endswith('QWindowOwnDCIcon'):
                counts['main-class matches'] += 1
        return True

    if not user32.EnumWindows(visit, 0):
        raise RuntimeError('Could not enumerate Paltalk windows.')
    main_windows = [hwnd for hwnd, name in windows if name.startswith('Qt') and name.endswith('QWindowOwnDCIcon')]
    if len(main_windows) == 1:
        return main_windows[0]
    if len(main_windows) > 1 or len(windows) != 1:
        guidance = ' Open Paltalk from its tray icon or restart it.' if not counts['title matches'] else ''
        raise PaltalkWindowNotFound(
            f"Paltalk's main window is unavailable or ambiguous "
            f"({len(pids)} Paltalk process(es); "
            + ', '.join(f'{key}: {value}' for key, value in counts.items()) + ').' + guidance,
            processes=len(pids), title_matches=counts['title matches'],
        )
    return windows[0][0]


def _wait_for_paltalk_main_window(user32, timeout=3.0):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return _paltalk_main_window(user32)
        except PaltalkWindowNotFound:
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))


def _desktop_context(user32):
    """Return the worker's session and desktop names for troubleshooting."""
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user32.GetThreadDesktop.restype = wintypes.HANDLE
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]

    def name(handle):
        if not handle:
            return 'unavailable'
        needed = wintypes.DWORD()
        user32.GetUserObjectInformationW(handle, 2, None, 0, ctypes.byref(needed))  # UOI_NAME
        if not needed.value:
            return 'unavailable'
        buf = ctypes.create_unicode_buffer((needed.value + 1) // 2)
        if not user32.GetUserObjectInformationW(handle, 2, buf, needed.value, ctypes.byref(needed)):
            return 'unavailable'
        return buf.value

    session = wintypes.DWORD()
    session_name = str(session.value) if kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)) else 'unavailable'
    worker = name(user32.GetThreadDesktop(kernel32.GetCurrentThreadId()))
    input_desktop = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
    try:
        interactive = name(input_desktop)
    finally:
        if input_desktop:
            user32.CloseDesktop(input_desktop)
    return f'session: {session_name}, worker desktop: {worker}, input desktop: {interactive}'


def _reopen_paltalk():
    """Launch the running Paltalk executable to bring its existing window back."""
    processes = [p for p in psutil.process_iter(['name', 'exe'])
                 if (p.info.get('name') or '').lower() == 'paltalk.exe']
    if len(processes) != 1:
        raise RuntimeError('Could not uniquely identify the running Paltalk process.')
    executable = processes[0].info.get('exe')
    if not executable or not Path(executable).is_file():
        raise RuntimeError('Could not access the running Paltalk executable.')
    subprocess.Popen([executable], cwd=str(Path(executable).parent))


def restore_paltalk():
    """Restore and maximize Paltalk, and verify it is ready before continuing."""
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    try:
        hwnd = _wait_for_paltalk_main_window(user32)
    except PaltalkWindowNotFound as exc:
        if exc.processes == 1 and exc.title_matches == 0:
            try:
                _reopen_paltalk()
                hwnd = _wait_for_paltalk_main_window(user32, timeout=5.0)
            except Exception as tray_exc:
                raise RuntimeError(f'Could not reopen Paltalk: {tray_exc}') from tray_exc
        else:
            try:
                context = _desktop_context(user32)
            except Exception:
                context = 'desktop context unavailable'
            raise PaltalkWindowNotFound(f'{exc} ({context})') from exc
    deadline = time.monotonic() + 5.0
    requested = None
    while True:
        if not user32.IsWindow(hwnd):
            try:
                hwnd = _paltalk_main_window(user32)
            except PaltalkWindowNotFound:
                hwnd = None
        if hwnd and user32.IsWindow(hwnd):
            ready = user32.IsWindowVisible(hwnd) and user32.IsZoomed(hwnd)
            if not ready and requested != hwnd:
                if not user32.ShowWindowAsync(hwnd, 3):  # SW_MAXIMIZE also restores minimized windows
                    raise RuntimeError('Windows could not request that Paltalk be maximized.')
                requested = hwnd
        else:
            ready = False
        if ready and user32.IsWindow(hwnd):
            try:
                selected = _paltalk_main_window(user32)
                if selected == hwnd:
                    return
                hwnd = selected
                requested = None
            except PaltalkWindowNotFound:
                pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Paltalk did not become visible and maximized within 5 seconds.')
        time.sleep(0.1)


def _close_buttons(a):
    """Find Paltalk buttons whose automation properties identify a close action."""
    windows = _paltalk_windows(a)
    if not windows:
        return None
    buttons = []
    for window in windows:
        for button in window.FindAll(a.TreeScope.Descendants,
                a.PropertyCondition(a.AutomationElement.ControlTypeProperty, a.ControlType.Button)):
            current = button.Current
            description = " ".join((current.AutomationId or "", current.Name or "", current.HelpText or "")).casefold()
            if "close" in description and current.IsEnabled:
                buttons.append(button)
    return buttons


def room_states(names):
    """Read the same close controls used to close rooms."""
    clr = import_module("clr")
    root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "assembly" / "GAC_MSIL"
    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        paths = sorted((root / assembly).glob(f"*/{assembly}.dll"))
        clr.AddReference(str(paths[-1]) if paths else assembly)
    a = import_module("System.Windows.Automation")
    buttons = _close_buttons(a)
    if buttons is None:
        return None
    states = {}
    for name in names:
        if name:
            matches = [button for button in buttons if name in (button.Current.AutomationId or "")]
            if len(matches) <= 1:
                states[name] = bool(matches)
    return states


def close_room(name, log):
    """Invoke the close button in the matching Paltalk room row."""
    clr = import_module("clr")
    gac_root = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Microsoft.NET" / "assembly" / "GAC_MSIL"
    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        paths = sorted((gac_root / assembly).glob(f"*/{assembly}.dll"))
        clr.AddReference(str(paths[-1]) if paths else assembly)
    a = import_module("System.Windows.Automation")
    buttons = _close_buttons(a)
    if buttons is None:
        log("Could not close room: Paltalk's window is unavailable.")
        return
    matches = [button for button in buttons if name in (button.Current.AutomationId or "")]
    if len(matches) != 1:
        log(f"Could not close room: {name}. {'Multiple matching rooms found' if matches else 'No matching open room found'}.")
        return
    matches[0].GetCurrentPattern(a.InvokePattern.Pattern).Invoke()
    log(f"Invoked close for room: {name}")


def open_rooms(names, delay, log, stopped):
    """Queue visible room tiles, then invoke them in order."""
    clr = import_module("clr")
    gac_root = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Microsoft.NET" / "assembly" / "GAC_MSIL"
    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        assembly_paths = sorted((gac_root / assembly).glob(f"*/{assembly}.dll"))
        if assembly_paths:
            clr.AddReference(str(assembly_paths[-1]))
        else:
            clr.AddReference(assembly)

    automation = import_module("System.Windows.Automation")
    and_condition = automation.AndCondition
    automation_element = automation.AutomationElement
    control_type = automation.ControlType
    invoke_pattern = automation.InvokePattern
    property_condition = automation.PropertyCondition
    tree_scope = automation.TreeScope

    pids = {
        process.info["pid"]
        for process in psutil.process_iter(["pid", "name"])
        if "paltalk" in (process.info.get("name") or "").lower()
    }
    if not pids:
        raise RuntimeError("Paltalk is not running. Start it and open the My Rooms / Rooms view.")

    desktop = automation_element.RootElement

    def find_visible_invoke_pattern(room_name):
        windows = desktop.FindAll(tree_scope.Children, property_condition(
            automation_element.ControlTypeProperty, control_type.Window))
        paltalk_windows = [window for window in windows if window.Current.ProcessId in pids]
        condition = and_condition(
            property_condition(automation_element.ControlTypeProperty, control_type.Button),
            property_condition(automation_element.NameProperty, room_name),
        )
        for window in paltalk_windows:
            try:
                buttons = window.FindAll(tree_scope.Descendants, condition)
                for button in buttons:
                    try:
                        current = button.Current
                        if not current.IsOffscreen and current.BoundingRectangle.Width > 0:
                            return button.GetCurrentPattern(invoke_pattern.Pattern)
                    except Exception:
                        continue
            except Exception:
                continue
        return None

    queued_rooms = []
    for name in names:
        pattern = find_visible_invoke_pattern(name)
        if pattern is None:
            log(f"Could not queue a visible room tile: {name}. Check the exact name and Rooms view.")
        else:
            queued_rooms.append((name, pattern))
            log(f"Queued room tile: {name}")

    for index, (name, pattern) in enumerate(queued_rooms):
        if stopped():
            log("Stopped.")
            return 0
        try:
            pattern.Invoke()
            log(f"Invoked room tile: {name}")
        except Exception:
            retry_pattern = find_visible_invoke_pattern(name)
            if retry_pattern is None:
                log(f"Could not invoke room tile: {name}. The Rooms view is no longer available.")
            else:
                try:
                    retry_pattern.Invoke()
                    log(f"Invoked room tile after retry: {name}")
                except Exception as exc:
                    log(f"Could not invoke room tile: {name}. {exc}")
        if index < len(queued_rooms) - 1:
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                if stopped():
                    log("Stopped.")
                    return 0
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    log("Finished.")
    return len(queued_rooms)
