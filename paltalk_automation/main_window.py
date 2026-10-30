"""Main application window."""

from pathlib import Path
import re

from PySide6.QtCore import QMimeData, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDrag, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QGraphicsDropShadowEffect, QInputDialog, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QStyle, QSystemTrayIcon, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import settings
from paltalk_automation.camera_opener.ui_tabs.camera_name_list import CameraNameDelegate, CameraNameList, LIVE_ROLE
from .foreground import ForegroundTracker
from paltalk_automation.camera_opener.ui_tabs.manual_camera_prompt import ManualCameraPromptController
from paltalk_automation.advert_blocker.ui_tabs.advert_blocker_tab import AdvertBlockerTab
from paltalk_automation.admin_actions.ui_tabs.admin_actions_tab import AdminActionsTab
from paltalk_automation.mic_timer.ui_tabs.mic_timer_tab import MicTimerTab
from paltalk_automation.room_opener.ui_tabs.room_opener_tab import RoomOpenerTab, RoomNameField, RoomDragHandle
from .styles import APP_STYLE
from .camera_opener.backend.camera_worker import CameraWorker
from .paltalk_process_worker import PaltalkProcessWorker
from .room_opener.backend.room_workers import CloseAllRoomsWorker, CloseRoomWorker, RecentRoomsWorker, RoomStateWorker, RoomWorker
from paltalk_automation.advert_blocker.backend.overlay import AdvertOverlay
from paltalk_automation.advert_blocker.backend.tracker import PaltalkTracker


class TextImportButton(QPushButton):
    fileDropped = Signal(str)

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _text_file(mime):
        urls = mime.urls() if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() == '.txt' and path.is_file():
                return str(path)
        return None

    def dragEnterEvent(self, event):
        if self._text_file(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._text_file(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.fileDropped.emit(path)
        else:
            event.ignore()


class CameraEntryField(QLineEdit):
    """Show duplicate feedback without replacing the username being typed."""

    def __init__(self):
        super().__init__()
        self.duplicate_message = QLabel('this name has already be been entered', self)
        self.duplicate_message.setStyleSheet('color: #e33b3b; background: transparent; padding: 0;')
        self.duplicate_message.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.duplicate_message.hide()
        self.setMinimumWidth(self.duplicate_message.sizeHint().width() + 150)

    def set_duplicate(self, duplicate):
        if bool(self.property('roomDuplicate')) != duplicate:
            self.setProperty('roomDuplicate', duplicate)
            self.style().unpolish(self)
            self.style().polish(self)
        self.duplicate_message.setVisible(duplicate)
        width = self.duplicate_message.sizeHint().width() if duplicate else 0
        self.setTextMargins(0, 0, width + 12 if duplicate else 0, 0)
        self._position_message()

    def _position_message(self):
        width = self.duplicate_message.sizeHint().width()
        self.duplicate_message.setGeometry(max(0, self.width() - width - 10), 0, width, self.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_message()


class MainWindow(QMainWindow):
    AUTO_OPEN_DELAY_MS = 5000
    AUTO_OPEN_MAX_ATTEMPTS = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paltalk Automation")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        self.resize(1000,
                    min(950, available.height()) if available else 950)
        self.setMinimumSize(850, 620)
        self.worker = None
        self.close_room_worker = None
        self.closing_other_room = None
        self.closing_all_rooms = False
        self.room_state_worker = None
        self.paltalk_process_worker = None
        self._pending_single_start = False
        self.recent_rooms_worker = None
        self.recent_rooms_manual_pending = False
        self.room_states = None
        self.other_open_names = []
        self.camera_worker = None
        self.camera_prompts = ManualCameraPromptController(self)
        self._closing_pending = False
        self._quitting = False
        self.tray_icon = None
        self.foreground_tracker = ForegroundTracker()
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
        self.room_opener_tab = RoomOpenerTab(self)
        self.auto_open_button = self.room_opener_tab.auto_open_button
        self.close_all_button = self.room_opener_tab.close_all_button
        self.delay = self.room_opener_tab.delay
        self.log = self.room_opener_tab.log
        self.mode_group = self.room_opener_tab.mode_group
        self.open_room_buttons = self.room_opener_tab.open_room_buttons
        self.other_rooms_layout = self.room_opener_tab.other_rooms_layout
        self.other_rooms_scroll = self.room_opener_tab.other_rooms_scroll
        self.recent_rooms_button = self.room_opener_tab.recent_rooms_button
        self.regular_button = self.room_opener_tab.regular_button
        self.room_labels = self.room_opener_tab.room_labels
        self.room_tray_status_label = self.room_opener_tab.room_tray_status_label
        self.rooms = self.room_opener_tab.rooms
        self.start_button = self.room_opener_tab.start_button
        self.vip_button = self.room_opener_tab.vip_button
        tabs.addTab(self.room_opener_tab, "Room Opener")
        self.create_camera_tab(tabs)
        self.advert_blocker_tab = AdvertBlockerTab(self.log)
        tabs.addTab(self.advert_blocker_tab, 'Advert Blocker')
        self.admin_actions_tab = AdminActionsTab(is_closing=lambda: self._closing_pending)
        tabs.addTab(self.admin_actions_tab, 'Admin Actions')
        self.mic_timer_tab = MicTimerTab(is_closing=lambda: self._closing_pending)
        tabs.addTab(self.mic_timer_tab, 'Mic Timer')
        self.setCentralWidget(tabs)
        # Measure after the inherited stylesheet has been applied to the button.
        self.start_button.setMinimumWidth(self.start_button.sizeHint().width())
        try:
            app_state = settings.load_app_state()
            selected_tab = app_state.get('selected_tab', 'room_opener')
            tabs.setCurrentIndex({'room_opener': 0, 'camera_opener': 1, 'advert_blocker': 2,
                                  'admin_actions': 3, 'timer': 4}.get(selected_tab, 0))
            self.start_in_tray.setChecked(bool(app_state.get('start_in_tray', False)))
            self.update_tray_status(self.start_in_tray.isChecked())
            self.advert_blocker_tab.advert_toggle.setChecked(app_state.get('advert_overlay_enabled') is True)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f'Could not load app state: {exc}')
        tabs.currentChanged.connect(self.save_selected_tab)
        self.start_in_tray.toggled.connect(self.save_start_in_tray)
        self.start_in_tray.toggled.connect(self.update_tray_status)
        self.advert_blocker_tab.advert_toggle.toggled.connect(self.advert_blocker_tab.set_advert_overlay_enabled)
        self.advert_blocker_tab.set_advert_overlay_enabled(self.advert_blocker_tab.advert_toggle.isChecked(), save=False)
        QApplication.instance().aboutToQuit.connect(self.advert_blocker_tab.advert_tracker.stop)

        self.start_button.clicked.connect(self.toggle_opening)
        self.close_all_button.clicked.connect(self.close_all_rooms)
        self.recent_rooms_button.clicked.connect(self.show_recent_rooms)
        self.mode_group.buttonClicked.connect(self.room_mode_changed)
        self.load_saved_settings()
        for field in self.rooms:
            field.textEdited.connect(lambda _text, room=field: self.room_text_edited(room))
            field.editingFinished.connect(lambda room=field: self.finish_room_edit(room))
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
        icon_path = Path(__file__).resolve().parent.parent / 'Icons' / 'Paltalk Automation.ico'
        icon = QIcon(str(icon_path))
        if icon.isNull():
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
            ("Portrait adjustment", self.camera_portrait_adjustment),
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
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and not self.isMinimized() and self.foreground_tracker.is_foreground(self):
                self.hide()
            else:
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
            seen = set()
            for index, field in enumerate(self.rooms, start=1):
                name = str(saved_rooms.get(f"room_{index}", ""))
                key = name.strip().casefold()
                if key and key in seen:
                    self.log.appendPlainText(f"Room {index} was cleared because its name duplicates another saved room.")
                    name = ''
                elif key:
                    seen.add(key)
                field.setText(name)
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

    def room_text_edited(self, field):
        for room in self.rooms:
            if room is field or room.property('roomDuplicate'):
                name = room.text().strip().casefold()
                duplicate = bool(name and any(other is not room and other.text().strip().casefold() == name
                                              for other in self.rooms))
                self.set_room_duplicate(room, duplicate)
        self.save_current_settings(announce=False)

    @staticmethod
    def set_room_duplicate(field, duplicate):
        if bool(field.property('roomDuplicate')) != duplicate:
            field.setProperty('roomDuplicate', duplicate)
            field.style().unpolish(field)
            field.style().polish(field)

    def finish_room_edit(self, field):
        name = field.text().strip()
        if name and any(other is not field and other.text().strip().casefold() == name.casefold()
                        for other in self.rooms):
            field.clear()
            self.set_room_duplicate(field, False)
            self.log.appendPlainText(f'Room "{name}" is already in the list; duplicate entry cleared.')
            self.save_current_settings(announce=False)

    def save_current_settings(self, announce=True):
        names = [field.text().strip().casefold() for field in self.rooms if field.text().strip()]
        if len(names) != len(set(names)):
            if announce:
                self.log.appendPlainText('Each configured room must have a different name.')
            return False
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
        if not check_existing:
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
        single_room_action = bool(self.worker and getattr(self.worker, 'check_existing', False))
        for index, (field, button) in enumerate(zip(self.rooms, self.open_room_buttons)):
            name = field.text().strip()
            known = self.room_states is not None and name in self.room_states
            is_open = known and self.room_states[name]
            highlight_open = bool(is_open and field.property('roomAvailable') is not False)
            if field.property("roomOpen") != highlight_open:
                field.setProperty("roomOpen", highlight_open)
                field.style().unpolish(field)
                field.style().polish(field)
            action = "Close" if is_open else "Open"
            button.setText(action)
            button.setAccessibleName(f"{action} Room {index + 1}")
            button.setToolTip(f"{action} the Paltalk room in Room {index + 1}" if known else "Restore Paltalk and check the room before opening")
            self.set_button_enabled(button, bool(
                name and field.property('roomAvailable') is not False
                and (not self.worker or single_room_action) and (not self.close_room_worker or getattr(self, 'closing_other_room', None)
                                         or getattr(self, 'closing_all_rooms', False))
            ))
        if hasattr(self, 'other_rooms_layout'):
            self.update_other_rooms()
        if hasattr(self, 'close_all_button'):
            self.set_button_enabled(self.close_all_button, bool(
                self.room_states is not None
                and (any(self.room_states.get(field.text().strip(), False) for field in self.rooms if field.text().strip())
                     or bool(getattr(self, 'other_open_names', [])))
                and (not self.worker or single_room_action) and (not self.close_room_worker or getattr(self, 'closing_other_room', None)
                                         or getattr(self, 'closing_all_rooms', False))
            ))

    def update_other_rooms(self):
        configured = {field.text().strip() for field in self.rooms
                      if field.text().strip() and field.property('roomAvailable') is not False}
        names = list(dict.fromkeys(name for name in self.other_open_names if name not in configured))
        rows = {}
        while self.other_rooms_layout.count():
            row = self.other_rooms_layout.takeAt(0).widget()
            if row:
                rows[row.property('roomName')] = row
        for name in names:
            row = rows.pop(name, None)
            if row is None:
                row = QWidget()
                row.setProperty('roomName', name)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                field = QLineEdit(name)
                field.setReadOnly(True)
                field.setProperty('roomOpen', True)
                button = QPushButton('Close')
                button.setAccessibleName(f'Close {name}')
                button.clicked.connect(lambda checked=False, room=name: self.close_other_room(room))
                row_layout.addWidget(field, 1)
                row_layout.addWidget(button)
            button = row.findChild(QPushButton)
            closing_name = getattr(self, 'closing_other_room', None)
            single_room_action = bool(self.worker and getattr(self.worker, 'check_existing', False))
            button.setEnabled((not self.worker or single_room_action) and (not self.close_room_worker or
                              bool(closing_name and closing_name != name) or
                              getattr(self, 'closing_all_rooms', False)))
            self.other_rooms_layout.addWidget(row)
        for row in rows.values():
            row.deleteLater()

    def close_other_room(self, name):
        if self.worker or self.close_room_worker:
            return
        self.closing_other_room = name
        self.close_room_worker = CloseRoomWorker(name)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
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
        self.closing_all_rooms = True
        self.close_room_worker = CloseAllRoomsWorker(names)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
        self.update_room_buttons()
        self.log.appendPlainText("Restoring Paltalk and checking open rooms...")
        self.close_room_worker.start()

    def close_room_finished(self):
        self.close_room_worker = None
        self.closing_other_room = None
        self.closing_all_rooms = False
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
        self.update_room_buttons()

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
        self.advert_blocker_tab.advert_tracker.stop()
        self.camera_prompts.clear()
        self.camera_restart_pending = False
        self.auto_open_pending = False
        running = False
        if self.mic_timer_tab.mic_timer_worker and self.mic_timer_tab.mic_timer_worker.isRunning():
            self.mic_timer_tab.mic_timer_worker.requestInterruption()
            running = True
        if self.admin_actions_tab.chat_reader_worker and self.admin_actions_tab.chat_reader_worker.isRunning():
            self.admin_actions_tab.chat_reader_worker.requestInterruption()
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
        self.foreground_tracker.close()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        event.accept()
        if self._quitting:
            QTimer.singleShot(0, QApplication.quit)

    def _finish_close_when_stopped(self):
        if ((self.mic_timer_tab.mic_timer_worker and self.mic_timer_tab.mic_timer_worker.isRunning()) or
                (self.admin_actions_tab.chat_reader_worker and self.admin_actions_tab.chat_reader_worker.isRunning()) or
                (self.camera_worker and self.camera_worker.isRunning()) or
                (self.worker and self.worker.isRunning()) or
                (self.close_room_worker and self.close_room_worker.isRunning()) or
                (self.room_state_worker and self.room_state_worker.isRunning()) or
                (self.recent_rooms_worker and self.recent_rooms_worker.isRunning()) or
                (self.paltalk_process_worker and self.paltalk_process_worker.isRunning())):
            QTimer.singleShot(100, self._finish_close_when_stopped)
        else:
            self.close()

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
        self.camera_import = TextImportButton('Import text')
        self.camera_import.setToolTip('Click or drop a text file to import usernames, one per line.')
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
        self.camera_names.setToolTip('A green dot marks a live camera detected in the visible room while monitoring. Drag to select usernames; press Delete or Remove selected to remove them.')
        self.camera_names_scroll = QScrollArea()
        self.camera_names_scroll.setWidgetResizable(True)
        self.camera_names_scroll.setWidget(self.camera_names)
        layout.addWidget(self.camera_names_scroll, 2)
        entry = QHBoxLayout()
        self.camera_entry = CameraEntryField()
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
        self.camera_portrait_adjustment = QPushButton()
        self.camera_portrait_adjustment.setObjectName('autoOpenButton')
        self.camera_portrait_adjustment.setCheckable(True)
        self.camera_portrait_adjustment.setChecked(True)
        self.camera_portrait_adjustment.setText('Portrait adjustment: On')

        
        self.camera_stop.setEnabled(False)
        for button in (self.camera_auto, self.camera_start, self.camera_stop, self.camera_portrait_adjustment):
            button.setFixedSize(200, 35)
            controls.addWidget(button)
        self.camera_start.setFixedSize(150, 35)
        self.camera_stop.setFixedSize(150, 35)
        controls.addStretch()
        layout.addLayout(controls)
        self.camera_manual_prompt = QPushButton('Prompt to add manually opened cameras: Off')
        self.camera_manual_prompt.setObjectName('autoOpenButton')
        self.camera_manual_prompt.setCheckable(True)
        self.camera_manual_prompt.setToolTip('While monitoring, prompt to add newly opened cameras in the visible room.')
        layout.addWidget(self.camera_manual_prompt, alignment=Qt.AlignmentFlag.AlignLeft)
        output = QHBoxLayout()

        def clear_log_button(label):
            button = QPushButton()
            button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(28, 28)
            button.setStyleSheet('padding: 0;')
            button.setToolTip(f'Clear {label} log')
            button.setAccessibleName(f'Clear {label} log')
            return button

        invoked_column = QVBoxLayout()
        invoked_header = QHBoxLayout()
        invoked_header.addWidget(QLabel('Opened Cameras'))
        invoked_clear = clear_log_button('Opened Cameras')
        invoked_header.addWidget(invoked_clear)
        invoked_column.addLayout(invoked_header)
        self.camera_invoked_log = QPlainTextEdit()
        self.camera_invoked_log.setReadOnly(True)
        invoked_clear.clicked.connect(self.camera_invoked_log.clear)
        invoked_column.addWidget(self.camera_invoked_log)
        output.addLayout(invoked_column, 1)
        failed_column = QVBoxLayout()
        failed_header = QHBoxLayout()
        failed_header.addWidget(QLabel('Could not open'))
        failed_clear = clear_log_button('Could not open')
        failed_header.addWidget(failed_clear)
        failed_column.addLayout(failed_header)
        self.camera_failed_log = QPlainTextEdit()
        self.camera_failed_log.setReadOnly(True)
        failed_clear.clicked.connect(self.camera_failed_log.clear)
        failed_column.addWidget(self.camera_failed_log)
        output.addLayout(failed_column, 1)
        activity_column = QVBoxLayout()
        activity_header = QHBoxLayout()
        activity_header.addWidget(QLabel('Other activity'))
        activity_clear = clear_log_button('Other activity')
        activity_header.addWidget(activity_clear)
        activity_column.addLayout(activity_header)
        self.camera_log = QPlainTextEdit()
        self.camera_log.setReadOnly(True)
        activity_clear.clicked.connect(self.camera_log.clear)
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
            manual_prompt = data.get('manual_camera_prompt', False)
            self.camera_manual_prompt.setChecked(manual_prompt if type(manual_prompt) is bool else False)
            self.camera_manual_prompt.setText('Prompt to add manually opened cameras: ' + ('On' if self.camera_manual_prompt.isChecked() else 'Off'))
            self.camera_auto.setChecked(bool(data.get('start_on_paltalk', False)))
            portrait_adjustment = data.get('portrait_adjustment', True)
            self.camera_portrait_adjustment.setChecked(portrait_adjustment if type(portrait_adjustment) is bool else True)
            self.camera_portrait_adjustment.setText(
                'Portrait adjustment: On' if self.camera_portrait_adjustment.isChecked() else 'Portrait adjustment: Off')
            self.camera_alphabetical.setChecked(bool(data.get('alphabetical', False)))
            if self.camera_alphabetical.isChecked():
                self.sort_camera_names(True)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.camera_log.appendPlainText(f'Could not load camera settings: {exc}')
        add.clicked.connect(self.add_camera_name)
        self.camera_import.clicked.connect(self.import_camera_names)
        self.camera_import.fileDropped.connect(self.import_camera_file)
        self.camera_export.clicked.connect(self.export_camera_names)
        self.camera_alphabetical.toggled.connect(self.camera_alphabetical_changed)
        self.camera_names.itemChanged.connect(self.camera_name_changed)
        self.camera_entry.textChanged.connect(self.update_camera_duplicate)
        model = self.camera_names.model()
        model.rowsInserted.connect(self.update_camera_duplicate)
        model.rowsRemoved.connect(self.update_camera_duplicate)
        model.dataChanged.connect(self.update_camera_duplicate)
        self.camera_entry.returnPressed.connect(self.add_camera_name)
        remove.clicked.connect(self.remove_camera_name)
        self.camera_auto.toggled.connect(self.camera_auto_changed)
        self.camera_portrait_adjustment.toggled.connect(self.camera_portrait_adjustment_changed)
        self.camera_manual_prompt.toggled.connect(self.camera_manual_prompt_changed)
        self.camera_start.clicked.connect(self.start_cameras)
        self.camera_stop.clicked.connect(self.stop_cameras)

    def update_camera_duplicate(self, *_args):
        name = self.camera_entry.text().strip().casefold()
        duplicate = bool(name and any(
            self.camera_names.item(i).text().strip().casefold() == name
            for i in range(self.camera_names.count())
        ))
        self.camera_entry.set_duplicate(duplicate)

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
        MainWindow.import_camera_file(self, filename)

    def import_camera_file(self, filename):
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
        blocked = self.camera_names.blockSignals(True)
        try:
            _item.setData(LIVE_ROLE, False)
        finally:
            self.camera_names.blockSignals(blocked)
        if self.camera_alphabetical.isChecked():
            self.sort_camera_names(True)
        self.update_camera_names()

    def update_camera_names(self):
        if self.save_camera_settings() and self.camera_worker:
            self.camera_worker.update_names(self.camera_username_list())

    def update_camera_live_status(self, names):
        live = {name.strip().casefold() for name in names}
        blocked = self.camera_names.blockSignals(True)
        try:
            for i in range(self.camera_names.count()):
                item = self.camera_names.item(i)
                is_live = item.text().strip().casefold() in live
                if bool(item.data(LIVE_ROLE)) != is_live:
                    item.setData(LIVE_ROLE, is_live)
        finally:
            self.camera_names.blockSignals(blocked)

    def camera_alphabetical_changed(self, enabled):
        self.sort_camera_names(enabled)
        self.save_camera_settings()

    def save_selected_tab(self, index):
        try:
            settings.save_app_state({0: 'room_opener', 1: 'camera_opener', 2: 'advert_blocker', 3: 'admin_actions', 4: 'timer'}.get(index, 'room_opener'))
        except OSError as exc:
            self.log.appendPlainText(f'Could not save app state: {exc}')

    def save_start_in_tray(self, enabled):
        try:
            settings.save_app_state(start_in_tray=enabled)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f'Could not save app state: {exc}')

    def update_tray_status(self, enabled):
        text = f'Start in tray: {"On" if enabled else "Off"}'
        self.admin_actions_tab.tray_status_label.setText(text)
        self.room_tray_status_label.setText(text)
        self.camera_tray_status_label.setText(text)

    def add_camera_name(self):
        name = self.camera_entry.text().strip()
        MainWindow.add_camera_username(self, name, clear_entry=True)

    def add_camera_username(self, name, clear_entry=False):
        name = name.strip()
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
            if clear_entry:
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
                                          self.camera_next_order, self.camera_portrait_adjustment.isChecked(),
                                          self.camera_manual_prompt.isChecked())
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

    def camera_portrait_adjustment_changed(self, enabled):
        self.camera_portrait_adjustment.setText('Portrait adjustment: On' if enabled else 'Portrait adjustment: Off')
        if self.camera_worker:
            self.camera_worker.update_portrait_adjustment(enabled)
        self.save_camera_settings()

    def camera_manual_prompt_changed(self, enabled):
        self.camera_manual_prompt.setText('Prompt to add manually opened cameras: ' + ('On' if enabled else 'Off'))
        if not enabled:
            self.camera_prompts.clear()
        if self.camera_worker:
            self.camera_worker.update_manual_prompt(enabled)
        self.save_camera_settings()

    def start_cameras(self, automatic=False):
        if self.camera_worker:
            return
        names = self.camera_username_list()
        if not names and not self.camera_manual_prompt.isChecked():
            self.camera_log.appendPlainText('Add at least one username before starting.')
            return
        if not self.save_camera_settings():
            return
        self.camera_worker = CameraWorker(names, self.camera_portrait_adjustment.isChecked(),
                                          self.camera_manual_prompt.isChecked())
        self.camera_worker.message.connect(self.camera_log.appendPlainText)
        self.camera_worker.invoked.connect(self.camera_invoked_log.appendPlainText)
        self.camera_worker.failed.connect(self.camera_failed_log.appendPlainText)
        self.camera_worker.live_status.connect(self.update_camera_live_status)
        self.camera_worker.manual_opened.connect(self.camera_prompts.queue)
        self.camera_worker.finished.connect(self.cameras_finished)
        self.camera_start.setEnabled(False)
        self.camera_stop.setEnabled(True)
        self.camera_log.appendPlainText('Camera monitoring started. Keep the On Cam list visible.')
        self.camera_worker.start()

    def stop_cameras(self):
        self.camera_prompts.clear()
        self.camera_restart_pending = False
        self.update_camera_live_status([])
        if self.camera_worker:
            self.camera_worker.requestInterruption()
            self.camera_stop.setEnabled(False)
            self.camera_log.appendPlainText('Stopping camera monitoring...')

    def cameras_finished(self):
        self.camera_prompts.clear()
        self.update_camera_live_status([])
        self.camera_worker = None
        self.camera_start.setEnabled(True)
        self.camera_stop.setEnabled(False)
        self.camera_log.appendPlainText('Camera monitoring stopped.')
        if self.camera_restart_pending:
            self.camera_restart_pending = False
            self.start_cameras()
