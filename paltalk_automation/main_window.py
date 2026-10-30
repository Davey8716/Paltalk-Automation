"""Main application window."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QMessageBox, QStyle, QSystemTrayIcon, QTabWidget, QToolButton,
)

from . import settings
from .camera_opener.ui_tabs.camera_opener_ui import CameraOpenerUi
from .room_opener.ui_tabs.room_opener_ui import RoomOpenerUi
from .foreground import ForegroundTracker
from .shutdown_coordinator import ShutdownCoordinator
from paltalk_automation.camera_opener.ui_tabs.manual_camera_prompt import ManualCameraPromptController
from paltalk_automation.advert_blocker.ui_tabs.advert_blocker_tab import AdvertBlockerTab
from paltalk_automation.admin_actions.ui_tabs.admin_actions_tab import AdminActionsTab
from paltalk_automation.mic_timer.ui_tabs.mic_timer_tab import MicTimerTab
from paltalk_automation.room_opener.ui_tabs.room_opener_tab import RoomOpenerTab
from .styles import APP_STYLE
from .paltalk_startup_coordinator import PaltalkStartupCoordinator



class MainWindow(CameraOpenerUi, RoomOpenerUi, QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paltalk Automation")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        self.resize(1000,
                    min(950, available.height()) if available else 950)
        self.setMinimumSize(850, 620)
        self.initialize_room_state()
        self.camera_worker = None
        self.camera_prompts = ManualCameraPromptController(self)
        self._closing_pending = False
        self.shutdown_coordinator = ShutdownCoordinator(self)
        self._quitting = False
        self.tray_icon = None
        self.foreground_tracker = ForegroundTracker()
        self.camera_restart_pending = False
        self.camera_auto_handled = False
        self.paltalk_was_running = False
        self.paltalk_startup = PaltalkStartupCoordinator(self)
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

        self.setup_room_controls()
        self.paltalk_startup.start()
        self.start_room_timers()
        self.setup_tray()






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

    def closeEvent(self, event):
        self.shutdown_coordinator.close_event(event)

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













