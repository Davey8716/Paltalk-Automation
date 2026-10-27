import json
import os
import sys
import time
from importlib import import_module
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit,
    QVBoxLayout, QWidget,
)
import psutil

APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "PaltalkRoomOpener"
SETTINGS = APP_DATA_DIR / "room_names.json"


def open_rooms(names, delay, log, stopped):
    # Load UI Automation on the worker thread; no UIA objects cross threads.
    clr = import_module("clr")
    gac_root = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Microsoft.NET" / "assembly" / "GAC_MSIL"
    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        assembly_paths = sorted((gac_root / assembly).glob(f"*/{assembly}.dll"))
        if assembly_paths:
            clr.AddReference(str(assembly_paths[-1]))
        else:
            # This works on machines whose .NET loader resolves GAC assemblies by name.
            clr.AddReference(assembly)
    automation = import_module("System.Windows.Automation")
    AndCondition = automation.AndCondition
    AutomationElement = automation.AutomationElement
    ControlType = automation.ControlType
    InvokePattern = automation.InvokePattern
    PropertyCondition = automation.PropertyCondition
    TreeScope = automation.TreeScope

    pids = set()
    for process in psutil.process_iter(["pid", "name"]):
        name = process.info.get("name") or ""
        if "paltalk" in name.lower():
            pids.add(process.info["pid"])
    if not pids:
        raise RuntimeError("Paltalk is not running. Start it and open the My Rooms / Rooms view.")

    desktop = AutomationElement.RootElement

    def find_visible_invoke_pattern(room_name):
        """Return an invoke pattern for the currently visible room tile, if any."""
        windows = desktop.FindAll(TreeScope.Children, PropertyCondition(
            AutomationElement.ControlTypeProperty, ControlType.Window))
        paltalk_windows = [window for window in windows if window.Current.ProcessId in pids]
        if not paltalk_windows:
            return None
        condition = AndCondition(
            PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button),
            PropertyCondition(AutomationElement.NameProperty, room_name),
        )
        for window in paltalk_windows:
            try:
                buttons = window.FindAll(TreeScope.Descendants, condition)
                for button in buttons:
                    try:
                        current = button.Current
                        if not current.IsOffscreen and current.BoundingRectangle.Width > 0:
                            return button.GetCurrentPattern(InvokePattern.Pattern)
                    except Exception:
                        continue
            except Exception:
                continue
        return None

    # Paltalk can hide the Rooms view as soon as the first room opens. Capture
    # every visible tile before invoking any of them so later rooms remain queued.
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
            return
        try:
            pattern.Invoke()
            log(f"Invoked room tile: {name}")
        except Exception:
            # A pattern can become stale after Paltalk redraws; search again as a fallback.
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
                    return
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    log("Finished.")


class RoomWorker(QThread):
    message = Signal(str)

    def __init__(self, names, delay):
        super().__init__()
        self.names = names
        self.delay = delay

    def run(self):
        try:
            open_rooms(self.names, self.delay, self.message.emit, self.isInterruptionRequested)
        except Exception as exc:
            self.message.emit(f"Error: {exc}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paltalk Automation")
        self.resize(650, 440)
        self.worker = None
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(QLabel("Enter the exact room tile names in the order you want to open them."))
        form = QFormLayout()
        self.rooms = []
        for i in range(5):
            field = QLineEdit()
            field.setPlaceholderText(f"Room {i + 1} name")
            form.addRow(f"Room {i + 1}:", field)
            self.rooms.append(field)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 60)
        self.delay.setValue(3)
        self.delay.setSuffix(" seconds")
        form.addRow("Delay between rooms:", self.delay)
        layout.addLayout(form)
        layout.addWidget(QLabel("Open Paltalk and display the My Rooms / Rooms view before starting."))
        buttons = QHBoxLayout()
        self.save_button = QPushButton("Save settings")
        self.start_button = QPushButton("Open rooms")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.setCentralWidget(root)
        self.save_button.clicked.connect(self.save_settings)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.load_settings()

    def load_settings(self):
        try:
            data = json.loads(SETTINGS.read_text(encoding="utf-8"))
            saved_rooms = data.get("rooms", {})
            if isinstance(saved_rooms, list):
                # Read the format written by earlier versions of the app.
                saved_rooms = {
                    f"room_{index}": value
                    for index, value in enumerate(saved_rooms, start=1)
                }
            for index, field in enumerate(self.rooms, start=1):
                field.setText(str(saved_rooms.get(f"room_{index}", "")))
            self.delay.setValue(float(data.get("delay", 3)))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f"Could not load settings: {exc}")

    def save_settings(self):
        try:
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps({
                "rooms": {
                    f"room_{index}": field.text()
                    for index, field in enumerate(self.rooms, start=1)
                },
                "delay": self.delay.value(),
            }, indent=2), encoding="utf-8")
            self.log.appendPlainText("Settings saved.")
            return True
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
            return False

    def start(self):
        names = [field.text().strip() for field in self.rooms if field.text().strip()]
        if not names:
            QMessageBox.warning(self, "No rooms", "Enter at least one room name.")
            return
        if not self.save_settings():
            return
        self.worker = RoomWorker(names, self.delay.value())
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.finished.connect(self.finished)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log.appendPlainText("Starting room opener...")
        self.worker.start()

    def stop(self):
        if self.worker:
            self.worker.requestInterruption()
            self.stop_button.setEnabled(False)
            self.log.appendPlainText("Stopping after the current operation...")

    def finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.worker = None

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

