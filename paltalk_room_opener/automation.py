"""Windows UI Automation routines for Paltalk room tiles."""

import os
import time
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


def _close_buttons(a):
    """Find Paltalk buttons whose automation properties identify a close action."""
    pids = {p.info["pid"] for p in psutil.process_iter(["pid", "name"])
            if (p.info.get("name") or "").lower() == "paltalk.exe"}
    if not pids:
        return None
    windows = a.AutomationElement.RootElement.FindAll(
        a.TreeScope.Children, a.PropertyCondition(a.AutomationElement.ControlTypeProperty, a.ControlType.Window))
    windows = [window for window in windows if window.Current.ProcessId in pids]
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
