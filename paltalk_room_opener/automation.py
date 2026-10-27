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
