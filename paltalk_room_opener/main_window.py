"""Main application window."""

from PySide6.QtCore import QMimeData, Qt, QTimer
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QButtonGroup, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from . import settings
from .automation import is_paltalk_running
from .styles import APP_STYLE
from .worker import CameraWorker, RoomWorker


class RoomNameField(QLineEdit):
    """Accept a room dragged from another room field or its handle."""

    def __init__(self, index, reorder):
        super().__init__()
        self.room_index = index
        self.reorder = reorder
        self.setDragEnabled(True)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if isinstance(event.source(), (RoomNameField, RoomDragHandle)):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if isinstance(event.source(), (RoomNameField, RoomDragHandle)):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        source = event.source()
        if isinstance(source, (RoomNameField, RoomDragHandle)):
            self.reorder(source.room_index, self.room_index)
            # CopyAction prevents QLineEdit from deleting its selected source text.
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dropEvent(event)


class RoomDragHandle(QLabel):
    def __init__(self, index):
        super().__init__('⋮⋮')
        self.room_index = index
        self.setToolTip('Drag to move this room to another position')
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, 'start_position')
                and (event.position().toPoint() - self.start_position).manhattanLength() >= 10):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText('room')
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)
        else:
            super().mouseMoveEvent(event)


class MainWindow(QMainWindow):
    AUTO_OPEN_DELAY_MS = 5000
    AUTO_OPEN_MAX_ATTEMPTS = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paltalk Automation")
        self.resize(1000, 720)
        self.setMinimumSize(850, 620)
        self.worker = None
        self.camera_worker = None
        self.camera_restart_pending = False
        self.camera_auto_handled = False
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = False
        self.paltalk_was_running = False
        self.setStyleSheet(APP_STYLE)

        tabs = QTabWidget()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 32, 38, 32)
        layout.setSpacing(18)
        layout.addWidget(QLabel("Enter exact room names. Drag a ⋮⋮ handle or selected text to reorder."))

        form = QFormLayout()
        self.rooms = []
        self.room_labels = []
        for index in range(5):
            field = RoomNameField(index, self.reorder_rooms)
            field.setPlaceholderText(f"Room {index + 1} name")
            label = QLabel(f"Room {index + 1}:")
            row = QHBoxLayout()
            row.addWidget(RoomDragHandle(index))
            row.addWidget(field)
            form.addRow(label, row)
            self.rooms.append(field)
            self.room_labels.append(label)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 60)
        self.delay.setValue(3)
        self.delay.setSuffix(" seconds")
        form.addRow("Delay between rooms:", self.delay)
        layout.addLayout(form)

        layout.addWidget(QLabel("Open Paltalk and display the My Rooms / Rooms view before starting."))
        buttons = QHBoxLayout()
        self.regular_button = QPushButton("Regular (3 rooms)")
        self.vip_button = QPushButton("VIP (5 rooms)")
        self.regular_button.setObjectName("regularModeButton")
        self.vip_button.setObjectName("vipModeButton")
        for button in (self.regular_button, self.vip_button):
            button.setCheckable(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.regular_button)
        self.mode_group.addButton(self.vip_button)
        self.regular_button.setChecked(True)

        self.auto_open_button = QPushButton("Open when Paltalk starts")
        self.auto_open_button.setObjectName("autoOpenButton")
        self.auto_open_button.setCheckable(True)

        self.save_button = QPushButton("Save settings")
        self.start_button = QPushButton("Open rooms")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        for button in (
            self.regular_button, self.vip_button, self.auto_open_button, self.save_button,
            self.start_button, self.stop_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        tabs.addTab(page, "Room Opener")
        self.create_camera_tab(tabs)
        self.setCentralWidget(tabs)
        try:
            selected_tab = settings.load_app_state().get('selected_tab', 'room_opener')
            tabs.setCurrentIndex(1 if selected_tab == 'camera_opener' else 0)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f'Could not load app state: {exc}')
        tabs.currentChanged.connect(self.save_selected_tab)

        self.save_button.clicked.connect(self.save_current_settings)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.mode_group.buttonClicked.connect(self.update_room_limit_appearance)
        self.load_saved_settings()
        self.update_room_limit_appearance()
        self.auto_open_button.toggled.connect(self.on_auto_open_toggled)
        self.paltalk_start_timer = QTimer(self)
        self.paltalk_start_timer.setInterval(1000)
        self.paltalk_start_timer.timeout.connect(self.check_for_paltalk_start)
        self.paltalk_start_timer.start()
        self.check_for_paltalk_start()

    def load_saved_settings(self):
        try:
            data = settings.load_settings()
            saved_rooms = data.get("rooms", {})
            if isinstance(saved_rooms, list):
                saved_rooms = {
                    f"room_{index}": value
                    for index, value in enumerate(saved_rooms, start=1)
                }
            for index, field in enumerate(self.rooms, start=1):
                field.setText(str(saved_rooms.get(f"room_{index}", "")))
            self.delay.setValue(float(data.get("delay", 3)))
            (self.vip_button if data.get("mode") == "vip" else self.regular_button).setChecked(True)
            self.auto_open_button.setChecked(bool(data.get("open_on_paltalk_start", False)))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f"Could not load settings: {exc}")

    def save_current_settings(self):
        try:
            settings.save_settings(
                [field.text() for field in self.rooms], self.delay.value(), self.selected_mode(),
                self.auto_open_button.isChecked(),
            )
            self.log.appendPlainText("Settings saved.")
            return True
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
            return False

    def start(self, automatic=False):
        mode = self.selected_mode()
        names = self.selected_room_names()
        if not names:
            if automatic:
                self.log.appendPlainText("Automatic opening skipped: no room names are configured.")
                self.auto_open_pending = False
                self.auto_open_handled_for_session = True
            else:
                QMessageBox.warning(self, "No rooms", "Enter at least one room name.")
            return
        if not self.save_current_settings():
            return
        if not automatic:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0
            self.auto_open_handled_for_session = True
        self.worker = RoomWorker(names, self.delay.value())
        self.worker.message.connect(self.log.appendPlainText)
        if automatic:
            self.worker.completed.connect(self.automatic_open_finished)
        self.worker.finished.connect(self.finished)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        prefix = "Automatically starting" if automatic else "Starting"
        self.log.appendPlainText(f"{prefix} {mode.title()} room opener with {len(names)} populated room(s)...")
        self.worker.start()

    def check_for_paltalk_start(self):
        paltalk_running = is_paltalk_running()
        if not paltalk_running:
            if self.paltalk_was_running:
                self.log.appendPlainText("Paltalk stopped. Automatic opening is ready for its next session.")
            self.paltalk_was_running = False
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0
            self.auto_open_handled_for_session = False
            self.camera_auto_handled = False
            return

        if not self.paltalk_was_running:
            self.paltalk_was_running = True
            self.log.appendPlainText("Paltalk detected.")
        if self.camera_auto.isChecked() and not self.camera_auto_handled:
            self.camera_auto_handled = True
            if not self.camera_worker:
                self.start_cameras(automatic=True)
        if (
            self.auto_open_button.isChecked()
            and not self.auto_open_handled_for_session
            and not self.auto_open_pending
            and not self.worker
        ):
            self.begin_automatic_opening("Waiting for Paltalk's Rooms view before opening rooms...")

    def on_auto_open_toggled(self, enabled):
        self.save_current_settings()
        if enabled:
            self.auto_open_handled_for_session = False
            self.check_for_paltalk_start()
        else:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0

    def begin_automatic_opening(self, message):
        self.auto_open_pending = True
        self.auto_open_attempts_remaining = self.AUTO_OPEN_MAX_ATTEMPTS
        self.log.appendPlainText(message)
        QTimer.singleShot(self.AUTO_OPEN_DELAY_MS, self.start_automatically)

    def start_automatically(self):
        if not self.auto_open_pending:
            return
        if self.auto_open_button.isChecked() and is_paltalk_running() and not self.worker:
            self.auto_open_attempts_remaining -= 1
            self.start(automatic=True)
        else:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0

    def automatic_open_finished(self, queued_room_count):
        if not self.auto_open_pending:
            return
        if queued_room_count > 0:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0
            self.auto_open_handled_for_session = True
            self.log.appendPlainText("Automatic opening completed for this Paltalk session.")
            return
        if self.auto_open_attempts_remaining > 0 and self.auto_open_button.isChecked():
            attempt = self.AUTO_OPEN_MAX_ATTEMPTS - self.auto_open_attempts_remaining + 1
            self.log.appendPlainText(
                f"Rooms view is not ready yet. Retrying automatic opening ({attempt}/{self.AUTO_OPEN_MAX_ATTEMPTS})..."
            )
            QTimer.singleShot(self.AUTO_OPEN_DELAY_MS, self.start_automatically)
        else:
            self.auto_open_pending = False
            self.auto_open_handled_for_session = True
            self.log.appendPlainText("Automatic opening stopped: no configured room tiles became available.")

    def selected_mode(self):
        return "vip" if self.vip_button.isChecked() else "regular"

    def reorder_rooms(self, source, destination):
        if source == destination or not (0 <= source < len(self.rooms) and 0 <= destination < len(self.rooms)):
            return
        names = [field.text() for field in self.rooms]
        if not names[source].strip():
            return
        names.insert(destination, names.pop(source))
        for field, name in zip(self.rooms, names):
            field.setText(name)
        self.save_current_settings()

    def selected_room_names(self):
        room_limit = 5 if self.selected_mode() == "vip" else 3
        return [field.text().strip() for field in self.rooms[:room_limit] if field.text().strip()]

    def update_room_limit_appearance(self):
        rooms_available = self.selected_mode() == "vip"
        for label, field in zip(self.room_labels[3:], self.rooms[3:]):
            label.setProperty("roomAvailable", rooms_available)
            field.setProperty("roomAvailable", rooms_available)
            label.style().unpolish(label)
            label.style().polish(label)
            field.style().unpolish(field)
            field.style().polish(field)

    def stop(self):
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = True
        if self.worker:
            self.worker.requestInterruption()
            self.stop_button.setEnabled(False)
            self.log.appendPlainText("Stopping after the current operation...")

    def finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.worker = None

    def closeEvent(self, event):
        self.camera_restart_pending = False
        if self.camera_worker and self.camera_worker.isRunning():
            self.camera_worker.requestInterruption()
            self.camera_worker.wait()
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()
        event.accept()

    def create_camera_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 32, 38, 32)
        layout.addWidget(QLabel('Monitor usernames in the visible On Cam list of the current room.'))
        self.camera_names = QListWidget()
        self.camera_names.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.camera_names.customContextMenuRequested.connect(self.camera_name_menu)
        layout.addWidget(self.camera_names)
        entry = QHBoxLayout()
        self.camera_entry = QLineEdit()
        self.camera_entry.setPlaceholderText('Exact Paltalk username')
        add = QPushButton('Add')
        remove = QPushButton('Remove selected')
        entry.addWidget(self.camera_entry)
        entry.addWidget(add)
        entry.addWidget(remove)
        layout.addLayout(entry)
        controls = QHBoxLayout()
        self.camera_auto = QPushButton('Start when Paltalk starts')
        self.camera_auto.setObjectName('autoOpenButton')
        self.camera_auto.setCheckable(True)
        save = QPushButton('Save settings')
        self.camera_start = QPushButton('Start')
        self.camera_stop = QPushButton('Stop')
        self.camera_stop.setEnabled(False)
        for button in (self.camera_auto, save, self.camera_start, self.camera_stop):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.camera_log = QPlainTextEdit()
        self.camera_log.setReadOnly(True)
        layout.addWidget(self.camera_log)
        tabs.addTab(page, 'Camera Opener')
        try:
            data = settings.load_camera_settings()
            names = data.get('usernames', [])
            if isinstance(names, list):
                self.camera_names.addItems([name for name in names if isinstance(name, str) and name.strip()])
                for index in range(self.camera_names.count()):
                    item = self.camera_names.item(index)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.camera_auto.setChecked(bool(data.get('start_on_paltalk', False)))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.camera_log.appendPlainText(f'Could not load camera settings: {exc}')
        add.clicked.connect(self.add_camera_name)
        self.camera_entry.returnPressed.connect(self.add_camera_name)
        remove.clicked.connect(self.remove_camera_name)
        save.clicked.connect(self.save_camera_settings)
        self.camera_auto.toggled.connect(self.camera_auto_changed)
        self.camera_start.clicked.connect(self.start_cameras)
        self.camera_stop.clicked.connect(self.stop_cameras)

    def camera_username_list(self):
        return [self.camera_names.item(i).text().strip() for i in range(self.camera_names.count())]

    def save_selected_tab(self, index):
        try:
            settings.save_app_state('camera_opener' if index == 1 else 'room_opener')
        except OSError as exc:
            self.log.appendPlainText(f'Could not save app state: {exc}')

    def add_camera_name(self):
        name = self.camera_entry.text().strip()
        if name and name.casefold() not in {n.casefold() for n in self.camera_username_list()}:
            self.camera_names.addItem(name)
            item = self.camera_names.item(self.camera_names.count() - 1)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.camera_entry.clear()

    def remove_camera_name(self):
        items = self.camera_names.selectedItems()
        if items:
            self.delete_camera_name(items[0])

    def camera_name_menu(self, position):
        item = self.camera_names.itemAt(position)
        if item is None:
            return
        menu = QMenu(self.camera_names)
        delete_action = menu.addAction('Delete username')
        if menu.exec(self.camera_names.viewport().mapToGlobal(position)) == delete_action:
            self.delete_camera_name(item)

    def delete_camera_name(self, item):
        row = self.camera_names.row(item)
        removed = self.camera_names.takeItem(row)
        if not self.save_camera_settings():
            self.camera_names.insertItem(row, removed)
        elif self.camera_worker:
            self.camera_restart_pending = bool(self.camera_username_list())
            self.camera_worker.requestInterruption()
            self.camera_stop.setEnabled(False)
            self.camera_log.appendPlainText('Updating monitored usernames...')

    def save_camera_settings(self):
        try:
            settings.save_camera_settings(self.camera_username_list(), self.camera_auto.isChecked())
            self.camera_log.appendPlainText('Camera settings saved.')
            return True
        except OSError as exc:
            QMessageBox.warning(self, 'Camera settings', f'Could not save settings: {exc}')
            return False

    def camera_auto_changed(self, enabled):
        self.save_camera_settings()
        if enabled:
            self.camera_auto_handled = False
            self.check_for_paltalk_start()

    def start_cameras(self, automatic=False):
        if self.camera_worker:
            return
        names = self.camera_username_list()
        if not names:
            self.camera_log.appendPlainText('Add at least one username before starting.')
            return
        if not self.save_camera_settings():
            return
        self.camera_worker = CameraWorker(names)
        self.camera_worker.message.connect(self.camera_log.appendPlainText)
        self.camera_worker.finished.connect(self.cameras_finished)
        self.camera_start.setEnabled(False)
        self.camera_stop.setEnabled(True)
        self.camera_log.appendPlainText('Camera monitoring started. Keep the On Cam list visible.')
        self.camera_worker.start()

    def stop_cameras(self):
        self.camera_restart_pending = False
        if self.camera_worker:
            self.camera_worker.requestInterruption()
            self.camera_stop.setEnabled(False)
            self.camera_log.appendPlainText('Stopping camera monitoring...')

    def cameras_finished(self):
        self.camera_worker = None
        self.camera_start.setEnabled(True)
        self.camera_stop.setEnabled(False)
        self.camera_log.appendPlainText('Camera monitoring stopped.')
        if self.camera_restart_pending:
            self.camera_restart_pending = False
            self.start_cameras()
