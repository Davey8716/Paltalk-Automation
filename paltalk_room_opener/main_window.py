"""Main application window."""

from pathlib import Path
import re

from PySide6.QtCore import QMimeData, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QDrag, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QGraphicsDropShadowEffect, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QStyle, QSystemTrayIcon, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import settings
from .camera_name_list import CameraNameDelegate, CameraNameList
from .styles import APP_STYLE
from .worker import CameraWorker, ChatReaderWorker, CloseAllRoomsWorker, CloseRoomWorker, MicTimerWorker, PaltalkProcessWorker, RecentRoomsWorker, RoomStateWorker, RoomWorker


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
    def __init__(self, index, reorder):
        super().__init__('⋮⋮')
        self.room_index = index
        self.reorder = reorder
        self.setObjectName('roomDragHandle')
        self.setAcceptDrops(True)
        self.setToolTip('Drag to move this room to another position')
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_highlighted(self, highlighted):
        self.setProperty('dragHighlight', highlighted)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event):
        if isinstance(event.source(), (RoomDragHandle, RoomNameField)) and event.source() is not self:
            self.set_highlighted(True)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if isinstance(event.source(), (RoomDragHandle, RoomNameField)) and event.source() is not self:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.set_highlighted(False)
        event.accept()

    def dropEvent(self, event):
        self.set_highlighted(False)
        source = event.source()
        if isinstance(source, (RoomDragHandle, RoomNameField)) and source is not self:
            self.reorder(source.room_index, self.room_index)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

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
            self.set_highlighted(True)
            try:
                drag.exec(Qt.DropAction.CopyAction)
            finally:
                self.set_highlighted(False)
        else:
            super().mouseMoveEvent(event)


class MainWindow(QMainWindow):
    AUTO_OPEN_DELAY_MS = 5000
    AUTO_OPEN_MAX_ATTEMPTS = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paltalk Automation")
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        self.resize(1000,
                    min(950, available.height()) if available else 950)
        self.setMinimumSize(850, 620)
        self.worker = None
        self.close_room_worker = None
        self.room_state_worker = None
        self.paltalk_process_worker = None
        self._pending_single_start = False
        self.recent_rooms_worker = None
        self.recent_rooms_manual_pending = False
        self.room_states = None
        self.other_open_names = []
        self.camera_worker = None
        self.mic_timer_worker = None
        self.chat_reader_worker = None
        self._closing_pending = False
        self._quitting = False
        self.tray_icon = None
        self.camera_restart_pending = False
        self.camera_auto_handled = False
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = False
        self.paltalk_was_running = False
        self.setStyleSheet(APP_STYLE)

        tabs = QTabWidget()
        menu_button = QToolButton(tabs)
        menu_button.setObjectName('settingsMenuButton')
        menu_icon = QPixmap(20, 20)
        menu_icon.fill(Qt.GlobalColor.transparent)
        painter = QPainter(menu_icon)
        for y in (3, 9, 15):
            painter.fillRect(2, y, 16, 3, Qt.GlobalColor.white)
        painter.end()
        menu_button.setIcon(QIcon(menu_icon))
        menu_button.setIconSize(QSize(20, 20))
        menu_button.setToolTip('Settings')
        menu_button.setAccessibleName('Settings')
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_menu = QMenu(menu_button)
        self.start_in_tray = settings_menu.addAction('Start in tray')
        self.start_in_tray.setCheckable(True)
        settings_menu.addAction('Open settings folder', self.open_settings_folder)
        menu_button.setMenu(settings_menu)
        tabs.setCornerWidget(menu_button, Qt.Corner.TopRightCorner)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 10, 38, 32)
        layout.setSpacing(18)
        self.room_tray_status_label = QLabel('Start in tray: Off')
        layout.addWidget(self.room_tray_status_label, alignment=Qt.AlignmentFlag.AlignRight)
        instruction_row = QHBoxLayout()
        instruction_row.addWidget(QLabel("Enter exact room names. Drag a ⋮⋮ handle or selected text to reorder."))
        recent_rooms_controls = QVBoxLayout()
        recent_rooms_controls.setSpacing(2)
        self.recent_rooms_button = QPushButton("Recently visited")
        self.recent_rooms_button.setFixedSize(150,35)
        recent_rooms_controls.addWidget(self.recent_rooms_button)
        instruction_row.addLayout(recent_rooms_controls)
        layout.addLayout(instruction_row)

        form = QGridLayout()
        form.setColumnStretch(2, 1)
        form.setColumnStretch(4, 1)
        self.rooms = []
        self.room_labels = []
        self.open_room_buttons = []
        for index in range(5):
            field = RoomNameField(index, self.reorder_rooms)
            field.setPlaceholderText(f"Room {index + 1} name")
            field.setMaximumWidth(580)
            label = QLabel(f"Room {index + 1}:")
            form.addWidget(RoomDragHandle(index, self.reorder_rooms), index, 0)
            form.addWidget(label, index, 1)
            form.addWidget(field, index, 2)
            open_button = QPushButton("Open")
            open_button.setEnabled(False)
            open_button.clicked.connect(lambda checked=False, i=index: self.toggle_configured_room(i))
            field.textChanged.connect(self.update_room_buttons)
            form.addWidget(open_button, index, 3)
            self.rooms.append(field)
            self.room_labels.append(label)
            self.open_room_buttons.append(open_button)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(5, 60)
        self.delay.setValue(5)
        self.delay.setSuffix(" seconds")
        self.delay.setMaximumWidth(580)
        form.addWidget(QLabel("Delay between rooms:"), 5, 0, 1, 2)
        form.addWidget(self.delay, 5, 2)
        self.start_button = QPushButton("Open rooms")
        form.addWidget(self.start_button, 5, 3)
        self.close_all_button = QPushButton("Close all")
        self.close_all_button.setEnabled(False)
        room_columns = QHBoxLayout()
        room_columns.addLayout(form, 3)
        other_panel = QVBoxLayout()
        other_panel.addWidget(QLabel('Other open rooms'))
        self.other_rooms_scroll = QScrollArea()
        self.other_rooms_scroll.setWidgetResizable(True)
        self.other_rooms_scroll.setMinimumWidth(250)
        self.other_rooms_scroll.setMaximumHeight(260)
        other_container = QWidget()
        self.other_rooms_layout = QVBoxLayout(other_container)
        self.other_rooms_layout.setContentsMargins(0, 0, 0, 0)
        self.other_rooms_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.other_rooms_scroll.setWidget(other_container)
        other_panel.addWidget(self.other_rooms_scroll)
        other_panel.addWidget(self.close_all_button, alignment=Qt.AlignmentFlag.AlignLeft)
        room_columns.addLayout(other_panel, 2)
        layout.addLayout(room_columns)

        layout.addWidget(QLabel("Open Paltalk and display the My Rooms / Rooms view before starting."))
        buttons = QHBoxLayout()
        self.regular_button = QPushButton("Regular (3 rooms)")
        self.vip_button = QPushButton("VIP (5 rooms)")
        self.regular_button.setObjectName("regularModeButton")
        self.vip_button.setObjectName("vipModeButton")
        for button in (self.regular_button, self.vip_button):
            button.setFixedSize(150,35)
            button.setCheckable(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.regular_button)
        self.mode_group.addButton(self.vip_button)
        self.regular_button.setChecked(True)

        self.auto_open_button = QPushButton("Open when Paltalk starts")
        self.auto_open_button.setFixedSize(180,35)
        self.auto_open_button.setObjectName("autoOpenButton")
        self.auto_open_button.setCheckable(True)

        for button in (
            self.regular_button, self.vip_button, self.auto_open_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        tabs.addTab(page, "Room Opener")
        self.create_camera_tab(tabs)
        self.create_admin_tab(tabs)
        self.create_timer_tab(tabs)
        tabs.setTabEnabled(2, False)
        tabs.setTabEnabled(3, False)
        self.setCentralWidget(tabs)
        try:
            app_state = settings.load_app_state()
            selected_tab = app_state.get('selected_tab', 'room_opener')
            tabs.setCurrentIndex({'room_opener': 0, 'camera_opener': 1}.get(selected_tab, 0))
            self.start_in_tray.setChecked(bool(app_state.get('start_in_tray', False)))
            self.update_tray_status(self.start_in_tray.isChecked())
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f'Could not load app state: {exc}')
        tabs.currentChanged.connect(self.save_selected_tab)
        self.start_in_tray.toggled.connect(self.save_start_in_tray)
        self.start_in_tray.toggled.connect(self.update_tray_status)

        self.start_button.clicked.connect(self.toggle_opening)
        self.close_all_button.clicked.connect(self.close_all_rooms)
        self.recent_rooms_button.clicked.connect(self.show_recent_rooms)
        self.mode_group.buttonClicked.connect(self.room_mode_changed)
        self.load_saved_settings()
        for field in self.rooms:
            field.textEdited.connect(lambda _text: self.save_current_settings(announce=False))
        self.delay.valueChanged.connect(lambda _value: self.save_current_settings(announce=False))
        self.update_room_limit_appearance()
        self.auto_open_button.toggled.connect(self.on_auto_open_toggled)
        self.paltalk_start_timer = QTimer(self)
        self.paltalk_start_timer.setInterval(1000)
        self.paltalk_start_timer.timeout.connect(self.check_for_paltalk_start)
        self.paltalk_start_timer.start()
        self.check_for_paltalk_start()
        self.room_state_timer = QTimer(self)
        self.room_state_timer.setInterval(3000)
        self.room_state_timer.timeout.connect(self.refresh_room_states)
        self.room_state_timer.start()
        self.refresh_room_states()
        self.recent_rooms_timer = QTimer(self)
        self.recent_rooms_timer.setInterval(1000)
        self.recent_rooms_timer.timeout.connect(self.refresh_recent_rooms)
        self.recent_rooms_timer.start()
        self.setup_tray()

    def show_recent_rooms(self):
        self.log.setFocus(Qt.FocusReason.OtherFocusReason)
        if self.recent_rooms_worker:
            if self.recent_rooms_worker.automatic:
                self.recent_rooms_manual_pending = True
                self.recent_rooms_button.setEnabled(False)
            return
        self.recent_rooms_button.setEnabled(False)
        self.start_recent_rooms_scan(automatic=False)

    def refresh_recent_rooms(self):
        if (self._quitting or not self.paltalk_was_running or self.recent_rooms_worker
                or self.worker or self.close_room_worker or self.room_state_worker):
            return
        self.start_recent_rooms_scan(automatic=True)

    def start_recent_rooms_scan(self, automatic):
        self.recent_rooms_worker = RecentRoomsWorker(automatic=automatic)
        self.recent_rooms_worker.result.connect(self.recent_rooms_received)
        self.recent_rooms_worker.finished.connect(self.recent_rooms_finished)
        self.recent_rooms_worker.start()

    def recent_rooms_finished(self):
        self.recent_rooms_worker = None
        if self.recent_rooms_manual_pending and not self._quitting:
            self.recent_rooms_manual_pending = False
            self.start_recent_rooms_scan(automatic=False)
            return
        self.recent_rooms_button.setEnabled(True)

    def recent_rooms_received(self, names, error):
        automatic = self.recent_rooms_worker and self.recent_rooms_worker.automatic
        if automatic:
            if not error and names:
                try:
                    settings.merge_recent_rooms(names)
                except (OSError, ValueError, TypeError) as exc:
                    self.log.appendPlainText(f'Could not save recently visited rooms: {exc}')
            return
        scanned_names = names
        try:
            names = settings.load_recent_rooms() if error else settings.merge_recent_rooms(names)
            if not error:
                names = list(dict.fromkeys([*(name for name in scanned_names if name in names), *names]))
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Recently visited", f"Could not read or save recent rooms: {exc}")
            return
        if error and not names:
            QMessageBox.warning(self, "Recently visited", error)
        dialog = QDialog(self)
        dialog.setWindowTitle("Recently visited rooms")
        font = dialog.font()
        font.setBold(True)
        dialog.setFont(font)
        dialog.resize(560, 400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select a room and click Copy, or double-click its name."))
        alphabetical = QPushButton('Alphabetical')
        alphabetical.setFixedSize(150,35)
        alphabetical.setCheckable(True)
        try:
            alphabetical.setChecked(bool(settings.load_app_state().get('recent_rooms_alphabetical', False)))
        except (OSError, ValueError, TypeError) as exc:
            self.log.appendPlainText(f'Could not load app state: {exc}')
        layout.addWidget(alphabetical)
        rooms = QListWidget()
        rooms.setStyleSheet('QListWidget { font-weight: bold; }')
        rooms.addItems(sorted(names, key=str.casefold) if alphabetical.isChecked() else names)
        layout.addWidget(rooms)
        if not names:
            layout.addWidget(QLabel("No recently visited rooms have been saved."))
        copy_button = QPushButton("Copy selected name")
        copy_button.setFixedSize(200,35)
        copy_button.setEnabled(False)
        def change_sort(enabled):
            try:
                if enabled:
                    settings.sort_recent_rooms()
                settings.save_app_state(recent_rooms_alphabetical=enabled)
            except (OSError, ValueError, TypeError) as exc:
                alphabetical.blockSignals(True)
                alphabetical.setChecked(not enabled)
                alphabetical.blockSignals(False)
                QMessageBox.warning(dialog, 'Recently visited', f'Could not save sort preference or room order: {exc}')
                return
            selected = rooms.currentItem().text() if rooms.currentItem() else None
            rooms.clear()
            rooms.addItems(sorted(names, key=str.casefold) if enabled else names)
            if selected is not None:
                matches = rooms.findItems(selected, Qt.MatchFlag.MatchExactly)
                if matches:
                    rooms.setCurrentItem(matches[0])
            copy_button.setEnabled(rooms.currentItem() is not None)
        alphabetical.toggled.connect(change_sort)
        feedback_timer = QTimer(dialog)
        feedback_timer.setSingleShot(True)
        def clear_copy_feedback():
            copy_button.setText("Copy selected name")
            copy_button.setStyleSheet("")
        feedback_timer.timeout.connect(clear_copy_feedback)
        rooms.itemClicked.connect(lambda item: copy_button.setEnabled(True))
        def copy_item(item):
            if item:
                copy_button.setEnabled(True)
                QApplication.clipboard().setText(item.text())
                copy_button.setText("Copied!")
                copy_button.setStyleSheet("QPushButton { background: #258c5a; color: white; }")
                feedback_timer.start(1200)
        copy_button.clicked.connect(lambda: copy_item(rooms.currentItem()))
        rooms.itemDoubleClicked.connect(copy_item)
        layout.addWidget(copy_button)
        dialog.exec()

    def open_settings_folder(self):
        try:
            settings.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(settings.APP_DATA_DIR))):
                raise OSError('Windows could not open the folder.')
        except OSError as exc:
            QMessageBox.warning(self, 'Settings folder', f'Could not open settings folder: {exc}')

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Paltalk Automation")
        menu = QMenu(self)
        menu.addAction("Open Paltalk Automation", self.restore_from_tray)
        room_action = menu.addAction("Open rooms")
        room_action.triggered.connect(self.start_button.click)
        def update_room_action():
            room_action.setText(self.start_button.text())
            room_action.setEnabled(self.start_button.isEnabled())
        menu.aboutToShow.connect(update_room_action)
        for text, button in (
            ("Start in tray", self.start_in_tray),
            ("Open rooms when Paltalk starts", self.auto_open_button),
            ("Start cameras when Paltalk starts", self.camera_auto),
        ):
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(button.isChecked())
            action.toggled.connect(button.setChecked)
            button.toggled.connect(action.setChecked)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_application)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()

    def restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_from_tray()

    def quit_application(self):
        self._quitting = True
        self.close()

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
            self.delay.setValue(float(data.get("delay", 5)))
            (self.vip_button if data.get("mode") == "vip" else self.regular_button).setChecked(True)
            self.auto_open_button.setChecked(bool(data.get("open_on_paltalk_start", False)))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f"Could not load settings: {exc}")

    def room_mode_changed(self):
        self.update_room_limit_appearance()
        try:
            settings.save_room_mode(self.selected_mode())
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            QMessageBox.warning(self, "Settings", f"Could not save room mode: {exc}")

    def save_current_settings(self, announce=True):
        try:
            settings.save_settings(
                [field.text() for field in self.rooms], self.delay.value(), self.selected_mode(),
                self.auto_open_button.isChecked(),
            )
            if announce:
                self.log.appendPlainText("Settings saved.")
            return True
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
            return False

    def toggle_opening(self):
        if self.worker:
            self.stop()
        else:
            self.start()

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
        self.start_room_worker(names, automatic, f"{mode.title()} room opener with {len(names)} populated room(s)")

    def open_configured_room(self, index):
        name = self.rooms[index].text().strip()
        if not name:
            self.log.appendPlainText(f"Enter a room name in Room {index + 1} before opening it.")
            return
        self.start_room_worker([name], False, f"room: {name}", check_existing=True)

    def start_room_worker(self, names, automatic, description, check_existing=False):
        if self.worker or self.close_room_worker or not self.save_current_settings():
            return
        if not automatic:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0
            self.auto_open_handled_for_session = True
        self.worker = RoomWorker(names, self.delay.value(), automatic=automatic, check_existing=check_existing)
        self.worker.message.connect(self.log.appendPlainText)
        if automatic:
            self.worker.completed.connect(self.automatic_open_finished)
        self.worker.finished.connect(self.finished)
        self.start_button.setText("Stop")
        self.start_button.setEnabled(True)
        for button in self.open_room_buttons:
            self.set_button_enabled(button, False)
        self.set_button_enabled(self.close_all_button, False)
        prefix = "Automatically starting" if automatic else "Starting"
        self.log.appendPlainText(f"{prefix} {description}...")
        if (check_existing or automatic) and self.room_state_worker:
            self._pending_single_start = True
            self.room_state_worker.requestInterruption()
            self.log.appendPlainText('Waiting for the room-status scan to stop...')
        else:
            self.worker.start()

    def check_for_paltalk_start(self):
        if self.paltalk_process_worker or self._quitting:
            return
        self.paltalk_process_worker = PaltalkProcessWorker()
        self.paltalk_process_worker.result.connect(self.paltalk_process_received)
        self.paltalk_process_worker.finished.connect(self.paltalk_process_finished)
        self.paltalk_process_worker.start()

    def paltalk_process_finished(self):
        self.paltalk_process_worker = None

    def paltalk_process_received(self, paltalk_running):
        if self._quitting:
            return
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
        if self.auto_open_button.isChecked() and self.paltalk_was_running and not self.worker:
            self.auto_open_attempts_remaining -= 1
            self.start(automatic=True)
        else:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0

    def automatic_open_finished(self, queued_room_count):
        if not self.auto_open_pending:
            return
        if queued_room_count > 0 or queued_room_count == RoomWorker.ALREADY_OPEN:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0
            self.auto_open_handled_for_session = True
            self.log.appendPlainText("Automatic opening completed for this Paltalk session.")
            return
        if self.auto_open_attempts_remaining > 0 and self.auto_open_button.isChecked():
            attempt = self.AUTO_OPEN_MAX_ATTEMPTS - self.auto_open_attempts_remaining + 1
            reason = ("Room status is unavailable" if queued_room_count == RoomWorker.STATE_UNAVAILABLE
                      else "Rooms view is not ready yet")
            self.log.appendPlainText(f"{reason}. Retrying automatic opening ({attempt}/{self.AUTO_OPEN_MAX_ATTEMPTS})...")
            QTimer.singleShot(self.AUTO_OPEN_DELAY_MS, self.start_automatically)
        else:
            self.auto_open_pending = False
            self.auto_open_handled_for_session = True
            reason = ("room status remained unavailable" if queued_room_count == RoomWorker.STATE_UNAVAILABLE
                      else "no configured room tiles became available")
            self.log.appendPlainText(f"Automatic opening stopped: {reason}.")

    def selected_mode(self):
        return "vip" if self.vip_button.isChecked() else "regular"

    def refresh_room_states(self):
        if (self.room_state_worker or self._quitting or self.close_room_worker or
                getattr(self, 'recent_rooms_worker', None) or
                (self.worker and (getattr(self.worker, 'check_existing', False) or getattr(self.worker, 'automatic', False)))):
            return
        self.room_state_worker = RoomStateWorker([field.text().strip() for field in self.rooms])
        self.room_state_worker.result.connect(self.room_states_received)
        self.room_state_worker.message.connect(self.log.appendPlainText)
        self.room_state_worker.finished.connect(self.room_state_finished)
        self.room_state_worker.start()

    def room_states_received(self, states):
        if self.worker and getattr(self.worker, 'check_existing', False):
            return
        if not self.close_room_worker and states is not None:
            if isinstance(states, dict) and 'states' in states and 'open_names' in states:
                self.room_states = states['states']
                self.other_open_names = states['open_names']
            else:
                self.room_states = states
        self.update_room_buttons()

    def room_state_finished(self):
        self.room_state_worker = None
        if self._pending_single_start:
            self._pending_single_start = False
            if self.worker and not self._quitting:
                self.worker.start()
            else:
                self.worker = None

    @staticmethod
    def set_button_enabled(button, enabled):
        # Disabling a focused button otherwise moves focus to the next field.
        if not enabled and button.hasFocus():
            button.clearFocus()
        button.setEnabled(enabled)

    def update_room_buttons(self):
        for index, (field, button) in enumerate(zip(self.rooms, self.open_room_buttons)):
            name = field.text().strip()
            known = self.room_states is not None and name in self.room_states
            is_open = known and self.room_states[name]
            if field.property("roomOpen") != bool(is_open):
                field.setProperty("roomOpen", bool(is_open))
                field.style().unpolish(field)
                field.style().polish(field)
            action = "Close" if is_open else "Open"
            button.setText(action)
            button.setAccessibleName(f"{action} Room {index + 1}")
            button.setToolTip(f"{action} the Paltalk room in Room {index + 1}" if known else "Restore Paltalk and check the room before opening")
            self.set_button_enabled(button, bool(name and not self.worker and not self.close_room_worker))
        if hasattr(self, 'other_rooms_layout'):
            self.update_other_rooms()
        if hasattr(self, 'close_all_button'):
            self.set_button_enabled(self.close_all_button, bool(
                self.room_states is not None
                and (any(self.room_states.get(field.text().strip(), False) for field in self.rooms if field.text().strip())
                     or bool(getattr(self, 'other_open_names', [])))
                and not self.worker and not self.close_room_worker
            ))

    def update_other_rooms(self):
        configured = {field.text().strip() for field in self.rooms if field.text().strip()}
        names = list(dict.fromkeys(name for name in self.other_open_names if name not in configured))
        while self.other_rooms_layout.count():
            item = self.other_rooms_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for name in names:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            field = QLineEdit(name)
            field.setReadOnly(True)
            field.setProperty('roomOpen', True)
            button = QPushButton('Close')
            button.setAccessibleName(f'Close {name}')
            button.setEnabled(not self.worker and not self.close_room_worker)
            button.clicked.connect(lambda checked=False, room=name: self.close_other_room(room))
            row_layout.addWidget(field, 1)
            row_layout.addWidget(button)
            self.other_rooms_layout.addWidget(row)

    def close_other_room(self, name):
        if self.worker or self.close_room_worker:
            return
        self.close_room_worker = CloseRoomWorker(name)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
        self.set_button_enabled(self.start_button, False)
        self.update_room_buttons()
        self.close_room_worker.start()

    def toggle_configured_room(self, index):
        self.open_configured_room(index)

    def close_configured_room(self, index):
        name = self.rooms[index].text().strip()
        if not name:
            self.log.appendPlainText(f"Enter a room name in Room {index + 1} before closing it.")
            return
        if self.close_room_worker:
            return
        self.close_room_worker = CloseRoomWorker(name)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
        self.set_button_enabled(self.start_button, False)
        self.update_room_buttons()
        self.close_room_worker.start()

    def close_all_rooms(self):
        if self.worker or self.close_room_worker:
            return
        names = list(dict.fromkeys(
            field.text().strip() for field in self.rooms
            if field.text().strip()
        ))
        names = list(dict.fromkeys(names + getattr(self, 'other_open_names', [])))
        if not names:
            return
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = True
        self.close_room_worker = CloseAllRoomsWorker(names)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
        self.set_button_enabled(self.start_button, False)
        self.update_room_buttons()
        self.log.appendPlainText("Restoring Paltalk and checking open rooms...")
        self.close_room_worker.start()

    def close_room_finished(self):
        self.close_room_worker = None
        self.start_button.setEnabled(True)
        self.update_room_buttons()
        self.refresh_room_states()

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
            if self._pending_single_start:
                self._pending_single_start = False
                self.log.appendPlainText('Stopped before opening the room.')
                self.finished()
                return
            self.worker.requestInterruption()
            self.start_button.setEnabled(False)
            self.log.appendPlainText("Stopping after the current operation...")

    def finished(self):
        self.start_button.setText("Open rooms")
        self.start_button.setEnabled(True)
        self.worker = None
        self.update_room_buttons()
        self.refresh_room_states()

    def closeEvent(self, event):
        if not self._quitting and self.tray_icon is not None:
            self.hide()
            event.ignore()
            return
        self.camera_restart_pending = False
        self.auto_open_pending = False
        running = False
        if self.mic_timer_worker and self.mic_timer_worker.isRunning():
            self.mic_timer_worker.requestInterruption()
            running = True
        if self.chat_reader_worker and self.chat_reader_worker.isRunning():
            self.chat_reader_worker.requestInterruption()
            running = True
        if self.camera_worker and self.camera_worker.isRunning():
            self.camera_worker.requestInterruption()
            running = True
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            running = True
        if self.close_room_worker and self.close_room_worker.isRunning():
            running = True
        if self.room_state_worker and self.room_state_worker.isRunning():
            running = True
        if self.recent_rooms_worker and self.recent_rooms_worker.isRunning():
            self.recent_rooms_worker.requestInterruption()
            running = True
        if self.paltalk_process_worker and self.paltalk_process_worker.isRunning():
            running = True
        if running:
            event.ignore()
            if not self._closing_pending:
                self._closing_pending = True
                self.camera_start.setEnabled(False)
                self.start_button.setEnabled(False)
                self.camera_log.appendPlainText('Stopping background work before closing...')
                QTimer.singleShot(100, self._finish_close_when_stopped)
            return
        if self.tray_icon is not None:
            self.tray_icon.hide()
        event.accept()
        if self._quitting:
            QTimer.singleShot(0, QApplication.quit)

    def _finish_close_when_stopped(self):
        if ((self.mic_timer_worker and self.mic_timer_worker.isRunning()) or
                (self.chat_reader_worker and self.chat_reader_worker.isRunning()) or
                (self.camera_worker and self.camera_worker.isRunning()) or
                (self.worker and self.worker.isRunning()) or
                (self.close_room_worker and self.close_room_worker.isRunning()) or
                (self.room_state_worker and self.room_state_worker.isRunning()) or
                (self.recent_rooms_worker and self.recent_rooms_worker.isRunning()) or
                (self.paltalk_process_worker and self.paltalk_process_worker.isRunning())):
            QTimer.singleShot(100, self._finish_close_when_stopped)
        else:
            self.close()

    def create_timer_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 10, 38, 32)
        layout.addWidget(QLabel('Time the person shown in Talking Now. Keep the room member list visible and unobscured.'))
        controls = QHBoxLayout()
        self.mic_timer_start = QPushButton('Start mic timer')
        self.mic_timer_stop = QPushButton('Stop mic timer')
        self.mic_timer_clear = QPushButton('Clear logs')
        self.mic_timer_stop.setEnabled(False)
        controls.addWidget(self.mic_timer_start)
        controls.addWidget(self.mic_timer_stop)
        controls.addWidget(self.mic_timer_clear)
        controls.addStretch()
        layout.addLayout(controls)
        self.mic_timer_status = QLabel('Start the timer to monitor the visible room.')
        self.mic_timer_status.setObjectName('micTimerStatus')
        self.mic_timer_status.setMinimumHeight(48)
        self.mic_timer_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.mic_timer_status.setWordWrap(True)
        layout.addWidget(self.mic_timer_status)
        self.mic_timer_rooms = {}
        self.mic_timer_logs = []
        columns = QHBoxLayout()
        for index in range(3):
            column = QVBoxLayout()
            column.addWidget(QLabel(f'Room {index + 1}'))
            log = QPlainTextEdit()
            log.setReadOnly(True)
            log.document().setMaximumBlockCount(2000)
            column.addWidget(log)
            self.mic_timer_logs.append(log)
            columns.addLayout(column)
        layout.addLayout(columns)
        tabs.addTab(page, 'Mic Timer')
        self.mic_timer_start.clicked.connect(self.start_mic_timer)
        self.mic_timer_stop.clicked.connect(self.stop_mic_timer)
        self.mic_timer_clear.clicked.connect(self.clear_mic_timer_logs)

    def clear_mic_timer_logs(self):
        for log in self.mic_timer_logs:
            log.clear()

    def log_mic_timer_room(self, room, message):
        room = tuple(room)
        if room not in self.mic_timer_rooms:
            if len(self.mic_timer_rooms) >= len(self.mic_timer_logs):
                self.mic_timer_status.setText('More than three rooms detected; only the first three have logs. Restart the timer to reassign them.')
                return
            self.mic_timer_rooms[room] = len(self.mic_timer_rooms)
        self.mic_timer_logs[self.mic_timer_rooms[room]].appendPlainText(message)

    def start_mic_timer(self):
        if self.mic_timer_worker:
            return
        self.mic_timer_worker = MicTimerWorker()
        self.mic_timer_rooms.clear()
        for log in self.mic_timer_logs:
            log.appendPlainText('— New timer session —')
        self.mic_timer_worker.message.connect(self.mic_timer_status.setText)
        self.mic_timer_worker.room_message.connect(self.log_mic_timer_room)
        self.mic_timer_worker.finished.connect(self.mic_timer_finished)
        self.mic_timer_start.setEnabled(False)
        self.mic_timer_stop.setEnabled(True)
        self.mic_timer_status.setText('Mic timer started; waiting for a confirmed speaker.')
        self.mic_timer_worker.start()

    def stop_mic_timer(self):
        if self.mic_timer_worker:
            self.mic_timer_worker.requestInterruption()
            self.mic_timer_stop.setEnabled(False)

    def mic_timer_finished(self):
        self.mic_timer_worker = None
        self.mic_timer_start.setEnabled(not self._closing_pending)
        self.mic_timer_stop.setEnabled(False)
        self.mic_timer_status.setText('Mic timer stopped.')

    def create_admin_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 10, 38, 32)
        self.tray_status_label = QLabel('Start in tray: Off')
        layout.addWidget(self.tray_status_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(QLabel('Banned phrases'))
        layout.addWidget(QLabel('Add literal phrases to monitor. Double-click a phrase to edit it.'))
        self.admin_phrases = QListWidget()
        self.admin_phrases.setObjectName('adminPhrases')
        layout.addWidget(self.admin_phrases)
        entry = QHBoxLayout()
        self.admin_phrase_entry = QLineEdit()
        self.admin_phrase_entry.setPlaceholderText('Enter or paste a banned phrase, including emoji')
        add = QPushButton('Add')
        edit = QPushButton('Edit selected')
        remove = QPushButton('Remove selected')
        for widget in (self.admin_phrase_entry, add, edit, remove):
            entry.addWidget(widget)
        layout.addLayout(entry)
        save = QPushButton('Save phrases')
        save.setFixedSize(150,35)
        layout.addWidget(save)
        layout.addWidget(QLabel('Selected room chat'))
        self.admin_chat_log = QPlainTextEdit()
        self.admin_chat_log.setReadOnly(True)
        self.admin_chat_log.document().setMaximumBlockCount(2000)
        layout.addWidget(self.admin_chat_log)
        chat_controls = QHBoxLayout()
        self.admin_chat_start = QPushButton('Start reading chat')
        self.admin_chat_stop = QPushButton('Stop reading chat')
        self.admin_chat_stop.setEnabled(False)
        clear = QPushButton('Clear log')
        for button in (self.admin_chat_start, self.admin_chat_stop, clear):
            chat_controls.addWidget(button)
        chat_controls.addStretch()
        layout.addLayout(chat_controls)
        review_label = QLabel('Review mode: new phrase matches are logged for inspection; no users are bounced.')
        review_label.setWordWrap(True)
        layout.addWidget(review_label)
        self.admin_match_log = QPlainTextEdit()
        self.admin_match_log.setReadOnly(True)
        self.admin_match_log.document().setMaximumBlockCount(2000)
        layout.addWidget(self.admin_match_log)
        clear_matches = QPushButton('Clear matches')
        clear_matches.setFixedSize(150,35)
        for button in (self.admin_chat_start, self.admin_chat_stop, clear):
            button.setFixedSize(180, 35)
        layout.addWidget(clear_matches)
        tabs.addTab(page, 'Admin Actions')
        try:
            for phrase in settings.load_admin_phrases():
                self.admin_phrases.addItem(phrase)
                item = self.admin_phrases.item(self.admin_phrases.count() - 1)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Admin actions', f'Could not load banned phrases: {exc}')
        add.clicked.connect(self.add_admin_phrase)
        self.admin_phrase_entry.returnPressed.connect(self.add_admin_phrase)
        edit.clicked.connect(self.edit_admin_phrase)
        remove.clicked.connect(self.remove_admin_phrase)
        save.clicked.connect(self.save_admin_phrases)
        self.admin_chat_start.clicked.connect(self.start_chat_reader)
        self.admin_chat_stop.clicked.connect(self.stop_chat_reader)
        clear.clicked.connect(self.admin_chat_log.clear)
        clear_matches.clicked.connect(self.admin_match_log.clear)

    def start_chat_reader(self):
        if self.chat_reader_worker is not None:
            return
        try:
            phrases = settings.load_admin_phrases()
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Admin actions', f'Could not load banned phrases: {exc}')
            return
        self.chat_reader_worker = ChatReaderWorker(phrases)
        self.chat_reader_worker.message.connect(self.admin_chat_log.appendPlainText)
        self.chat_reader_worker.match.connect(self.admin_match_log.appendPlainText)
        self.admin_match_log.appendPlainText(f'Review mode started with {len(phrases)} saved phrases. Existing messages are ignored; no users will be bounced.')
        self.chat_reader_worker.finished.connect(self.chat_reader_finished)
        self.admin_chat_start.setEnabled(False)
        self.admin_chat_stop.setEnabled(True)
        self.chat_reader_worker.start()

    def stop_chat_reader(self):
        if self.chat_reader_worker:
            self.chat_reader_worker.requestInterruption()
            self.admin_chat_stop.setEnabled(False)

    def chat_reader_finished(self):
        self.chat_reader_worker = None
        self.admin_chat_start.setEnabled(not self._closing_pending)
        self.admin_chat_stop.setEnabled(False)
        self.admin_chat_log.appendPlainText('Chat reader stopped.')

    def add_admin_phrase(self):
        phrase = self.admin_phrase_entry.text().strip()
        if not phrase:
            return
        if phrase.casefold() in {self.admin_phrases.item(i).text().strip().casefold()
                                for i in range(self.admin_phrases.count())}:
            QMessageBox.warning(self, 'Admin actions', 'That phrase is already in the list.')
            return
        self.admin_phrases.addItem(phrase)
        item = self.admin_phrases.item(self.admin_phrases.count() - 1)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.admin_phrases.setCurrentItem(item)
        self.admin_phrase_entry.clear()

    def edit_admin_phrase(self):
        item = self.admin_phrases.currentItem()
        if item:
            self.admin_phrases.editItem(item)

    def remove_admin_phrase(self):
        row = self.admin_phrases.currentRow()
        if row >= 0:
            item = self.admin_phrases.takeItem(row)
            if not self.save_admin_phrases():
                self.admin_phrases.insertItem(row, item)
                self.admin_phrases.setCurrentItem(item)

    def save_admin_phrases(self):
        phrases = [self.admin_phrases.item(i).text().strip() for i in range(self.admin_phrases.count())]
        if any(not phrase for phrase in phrases) or len({p.casefold() for p in phrases}) != len(phrases):
            QMessageBox.warning(self, 'Admin actions', 'Phrases cannot be empty or duplicated.')
            return False
        try:
            settings.save_admin_phrases(phrases)
            return True
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Admin actions', f'Could not save banned phrases: {exc}')
            return False

    def create_camera_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 10, 38, 32)
        self.camera_tray_status_label = QLabel('Start in tray: Off')
        layout.addWidget(self.camera_tray_status_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(QLabel('Monitor up to 200 usernames in the visible On Cam list of the rooms you enter.\n' \
        'This is a global camera monitor across rooms and is not room specific.'))
        sort_controls = QHBoxLayout()
        sort_controls.addStretch()
        self.camera_alphabetical = QPushButton('Alphabetical')
        self.camera_alphabetical.setObjectName('cameraAlphabetical')
        self.camera_alphabetical.setCheckable(True)
        sort_controls.addWidget(self.camera_alphabetical)
        self.camera_import = QPushButton('Import text')
        self.camera_import.setToolTip('Import usernames from a text file, one per line.')
        sort_controls.addWidget(self.camera_import)
        self.camera_export = QPushButton('Export to text')
        self.camera_export.setToolTip('Export the camera usernames to a text file.')
        self.camera_export_glow = QGraphicsDropShadowEffect(self.camera_export)
        self.camera_export_glow.setColor(QColor('#00cfff'))
        self.camera_export_glow.setBlurRadius(24)
        self.camera_export_glow.setOffset(0, 0)
        self.camera_export_glow.setEnabled(False)
        self.camera_export.setGraphicsEffect(self.camera_export_glow)
        self.camera_export_flash = QTimer(self)
        self.camera_export_flash.setInterval(2000)
        self.camera_export_flash.timeout.connect(self.flash_camera_export)
        self.camera_export_flashes_left = 0
        sort_controls.addWidget(self.camera_export)
        layout.addLayout(sort_controls)
        self.camera_names = CameraNameList()
        self.camera_next_order = 1
        self.camera_names.setItemDelegate(CameraNameDelegate(self.camera_names))
        self.camera_names.setObjectName('cameraNames')
        self.camera_names.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.camera_names.customContextMenuRequested.connect(self.camera_name_menu)
        self.camera_names.deleteRequested.connect(self.remove_camera_name)
        self.camera_names.setToolTip('Drag to select usernames. Use Ctrl or Shift to select more, then press Delete or Remove selected.')
        self.camera_names_scroll = QScrollArea()
        self.camera_names_scroll.setWidgetResizable(True)
        self.camera_names_scroll.setWidget(self.camera_names)
        layout.addWidget(self.camera_names_scroll, 2)
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
        
        self.camera_start = QPushButton('Start')
        self.camera_stop = QPushButton('Stop')

        
        self.camera_stop.setEnabled(False)
        for button in (self.camera_auto, self.camera_start, self.camera_stop):
            button.setFixedSize(200, 35)
            controls.addWidget(button)
        self.camera_start.setFixedSize(150, 35)
        self.camera_stop.setFixedSize(150, 35)
        controls.addStretch()
        layout.addLayout(controls)
        output = QHBoxLayout()
        invoked_column = QVBoxLayout()
        invoked_column.addWidget(QLabel('Opened Cameras'))
        self.camera_invoked_log = QPlainTextEdit()
        self.camera_invoked_log.setReadOnly(True)
        invoked_column.addWidget(self.camera_invoked_log)
        output.addLayout(invoked_column, 1)
        failed_column = QVBoxLayout()
        failed_column.addWidget(QLabel('Could not open'))
        self.camera_failed_log = QPlainTextEdit()
        self.camera_failed_log.setReadOnly(True)
        failed_column.addWidget(self.camera_failed_log)
        output.addLayout(failed_column, 1)
        activity_column = QVBoxLayout()
        activity_column.addWidget(QLabel('Other activity'))
        self.camera_log = QPlainTextEdit()
        self.camera_log.setReadOnly(True)
        activity_column.addWidget(self.camera_log)
        output.addLayout(activity_column, 1)
        layout.addLayout(output, 1)
        tabs.addTab(page, 'Camera Opener')
        try:
            data = settings.load_camera_settings()
            names = data.get('usernames', [])
            if isinstance(names, list):
                numbers = data.get('username_numbers', [])
                valid_numbers = (isinstance(numbers, list) and len(numbers) == len(names)
                                 and all(type(n) is int and n > 0 for n in numbers)
                                 and len(set(numbers)) == len(numbers))
                for index, name in enumerate(names):
                    if not isinstance(name, str) or not name.strip():
                        continue
                    self.camera_names.addItem(name)
                    item = self.camera_names.item(self.camera_names.count() - 1)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    number = numbers[index] if valid_numbers else index + 1
                    item.setData(Qt.ItemDataRole.UserRole, number)
                    self.camera_next_order = max(self.camera_next_order, number + 1)
                self.renumber_camera_names()
            self.camera_auto.setChecked(bool(data.get('start_on_paltalk', False)))
            self.camera_alphabetical.setChecked(bool(data.get('alphabetical', False)))
            if self.camera_alphabetical.isChecked():
                self.sort_camera_names(True)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.camera_log.appendPlainText(f'Could not load camera settings: {exc}')
        add.clicked.connect(self.add_camera_name)
        self.camera_import.clicked.connect(self.import_camera_names)
        self.camera_export.clicked.connect(self.export_camera_names)
        self.camera_alphabetical.toggled.connect(self.camera_alphabetical_changed)
        self.camera_names.itemChanged.connect(self.camera_name_changed)
        self.camera_entry.returnPressed.connect(self.add_camera_name)
        remove.clicked.connect(self.remove_camera_name)
        self.camera_auto.toggled.connect(self.camera_auto_changed)
        self.camera_start.clicked.connect(self.start_cameras)
        self.camera_stop.clicked.connect(self.stop_cameras)

    def camera_username_list(self):
        items = [self.camera_names.item(i) for i in range(self.camera_names.count())]
        return [item.text().strip() for item in sorted(items, key=lambda item: item.data(Qt.ItemDataRole.UserRole))]

    def renumber_camera_names(self):
        items = sorted((self.camera_names.item(i) for i in range(self.camera_names.count())),
                       key=lambda item: item.data(Qt.ItemDataRole.UserRole))
        signals_blocked = self.camera_names.blockSignals(True)
        try:
            for number, item in enumerate(items, 1):
                item.setData(Qt.ItemDataRole.UserRole, number)
        finally:
            self.camera_names.blockSignals(signals_blocked)
        self.camera_next_order = len(items) + 1

    def import_camera_names(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Import usernames', '', 'Text files (*.txt);;All files (*)')
        if not filename:
            return
        try:
            lines = Path(filename).read_text(encoding='utf-8-sig').splitlines()
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Import usernames', f'Could not read usernames: {exc}')
            return
        existing = {self.camera_names.item(i).text().strip().casefold() for i in range(self.camera_names.count())}
        names = []
        for line in lines:
            name = re.sub(r'^\s*\d+\.\s+', '', line).strip()
            if name and name.casefold() not in existing:
                names.append(name)
                existing.add(name.casefold())
        if self.camera_names.count() + len(names) > 200:
            QMessageBox.warning(self, 'Import usernames', 'Import would exceed the 200 username limit. No usernames were added.')
            return
        if not names:
            QMessageBox.information(self, 'Import usernames', 'No new usernames were found.')
            return
        previous_order = self.camera_next_order
        added = []
        blocked = self.camera_names.blockSignals(True)
        try:
            for name in names:
                self.camera_names.addItem(name)
                item = self.camera_names.item(self.camera_names.count() - 1)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, self.camera_next_order)
                self.camera_next_order += 1
                added.append(item)
            if self.camera_alphabetical.isChecked():
                self.sort_camera_names(True)
        finally:
            self.camera_names.blockSignals(blocked)
        if not self.save_camera_settings():
            for item in added:
                self.camera_names.takeItem(self.camera_names.row(item))
            self.camera_next_order = previous_order
            return
        if self.camera_worker:
            self.camera_worker.update_names(self.camera_username_list())
        self.remind_camera_export()
        self.camera_log.appendPlainText(f'Imported {len(names)} username(s).')

    def export_camera_names(self):
        names = [(self.camera_names.item(i).data(Qt.ItemDataRole.UserRole) or i + 1,
                  self.camera_names.item(i).text().strip()) for i in range(self.camera_names.count())]
        names = [(number, name) for number, name in names if name]
        if not names:
            QMessageBox.information(self, 'Export usernames', 'There are no usernames to export.')
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Export usernames', 'camera-usernames.txt', 'Text files (*.txt)')
        if not filename:
            return
        try:
            Path(filename).write_text(''.join(f'{number}. {name}\n' for number, name in names),
                                      encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self, 'Export usernames', f'Could not export usernames: {exc}')
        else:
            self.clear_camera_export_reminder()

    def flash_camera_export(self):
        highlighted = not self.camera_export.property('exportHighlight')
        self.camera_export.setProperty('exportHighlight', self.camera_export_flash_color if highlighted else '')
        self.camera_export_glow.setEnabled(highlighted)
        self.camera_export.style().unpolish(self.camera_export)
        self.camera_export.style().polish(self.camera_export)
        self.camera_export.update()
        self.camera_export_flashes_left -= 1
        if self.camera_export_flashes_left <= 0:
            self.camera_export_flash.stop()

    def remind_camera_export(self, color='green'):
        self.camera_export.setToolTip('Usernames have changed. Export to text to save an updated list.')
        self.camera_export_flash.stop()
        self.camera_export.setProperty('exportHighlight', '')
        self.camera_export_glow.setEnabled(False)
        self.camera_export_flash_color = color
        self.camera_export_glow.setColor(QColor('#20c86a' if color == 'green' else '#ed4b4b'))
        self.camera_export_flashes_left = 2
        self.flash_camera_export()
        self.camera_export_flash.start()

    def clear_camera_export_reminder(self):
        self.camera_export_flash.stop()
        self.camera_export.setProperty('exportHighlight', '')
        self.camera_export_glow.setEnabled(False)
        self.camera_export.style().unpolish(self.camera_export)
        self.camera_export.style().polish(self.camera_export)
        self.camera_export.update()
        self.camera_export.setToolTip('Export the camera usernames to a text file.')

    def sort_camera_names(self, alphabetical):
        items = [self.camera_names.takeItem(0) for _ in range(self.camera_names.count())]
        if alphabetical:
            items.sort(key=lambda item: (item.text().casefold(), item.data(Qt.ItemDataRole.UserRole)))
        else:
            items.sort(key=lambda item: item.data(Qt.ItemDataRole.UserRole))
        for item in items:
            self.camera_names.addItem(item)

    def camera_name_changed(self, _item):
        if self.camera_alphabetical.isChecked():
            self.sort_camera_names(True)
        self.update_camera_names()

    def update_camera_names(self):
        if self.save_camera_settings() and self.camera_worker:
            self.camera_worker.update_names(self.camera_username_list())

    def camera_alphabetical_changed(self, enabled):
        self.sort_camera_names(enabled)
        self.save_camera_settings()

    def save_selected_tab(self, index):
        try:
            settings.save_app_state({0: 'room_opener', 1: 'camera_opener', 2: 'admin_actions', 3: 'timer'}.get(index, 'room_opener'))
        except OSError as exc:
            self.log.appendPlainText(f'Could not save app state: {exc}')

    def save_start_in_tray(self, enabled):
        try:
            settings.save_app_state(start_in_tray=enabled)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f'Could not save app state: {exc}')

    def update_tray_status(self, enabled):
        text = f'Start in tray: {"On" if enabled else "Off"}'
        self.tray_status_label.setText(text)
        self.room_tray_status_label.setText(text)
        self.camera_tray_status_label.setText(text)

    def add_camera_name(self):
        name = self.camera_entry.text().strip()
        if name and name.casefold() not in {n.casefold() for n in self.camera_username_list()}:
            if self.camera_names.count() >= 200:
                QMessageBox.warning(self, 'Camera usernames', 'The list can contain up to 200 usernames.')
                return
            self.camera_names.blockSignals(True)
            self.camera_names.addItem(name)
            item = self.camera_names.item(self.camera_names.count() - 1)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(Qt.ItemDataRole.UserRole, self.camera_next_order)
            self.camera_next_order += 1
            self.camera_names.blockSignals(False)
            if self.camera_alphabetical.isChecked():
                self.sort_camera_names(True)
            self.camera_names.setCurrentItem(item)
            self.camera_names.scrollToItem(item)
            self.camera_names_scroll.ensureVisible(0, self.camera_names.visualItemRect(item).center().y())
            self.camera_entry.clear()
            self.update_camera_names()
            self.remind_camera_export()

    def remove_camera_name(self):
        items = self.camera_names.selectedItems()
        if items:
            self.delete_camera_names(items)

    def camera_name_menu(self, position):
        item = self.camera_names.itemAt(position)
        if item is None:
            return
        menu = QMenu(self.camera_names)
        items = self.camera_names.selectedItems() if item.isSelected() else [item]
        delete_action = menu.addAction('Delete selected usernames' if len(items) > 1 else 'Delete username')
        if menu.exec(self.camera_names.viewport().mapToGlobal(position)) == delete_action:
            self.delete_camera_names(items)

    def delete_camera_name(self, item):
        MainWindow.delete_camera_names(self, [item])

    def delete_camera_names(self, items):
        rows = sorted(self.camera_names.row(item) for item in items if self.camera_names.row(item) >= 0)
        if not rows:
            return
        old_numbers = [(self.camera_names.item(i), self.camera_names.item(i).data(Qt.ItemDataRole.UserRole))
                       for i in range(self.camera_names.count())]
        old_next_order = self.camera_next_order
        removed = [(row, self.camera_names.takeItem(row)) for row in reversed(rows)]
        self.renumber_camera_names()
        if not self.save_camera_settings():
            for row, item in reversed(removed):
                self.camera_names.insertItem(row, item)
                item.setSelected(True)
            signals_blocked = self.camera_names.blockSignals(True)
            try:
                for original_item, number in old_numbers:
                    original_item.setData(Qt.ItemDataRole.UserRole, number)
            finally:
                self.camera_names.blockSignals(signals_blocked)
            self.camera_next_order = old_next_order
        else:
            if self.camera_worker:
                self.camera_worker.update_names(self.camera_username_list())
            self.remind_camera_export('red')

    def save_camera_settings(self):
        try:
            items = sorted((self.camera_names.item(i) for i in range(self.camera_names.count())),
                           key=lambda item: item.data(Qt.ItemDataRole.UserRole))
            settings.save_camera_settings(self.camera_username_list(), self.camera_auto.isChecked(),
                                          self.camera_alphabetical.isChecked(),
                                          [item.data(Qt.ItemDataRole.UserRole) for item in items],
                                          self.camera_next_order)
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
        self.camera_worker.invoked.connect(self.camera_invoked_log.appendPlainText)
        self.camera_worker.failed.connect(self.camera_failed_log.appendPlainText)
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
