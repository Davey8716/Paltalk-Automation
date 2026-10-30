"""Main application window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
)

from . import settings
from .camera_opener.ui_tabs.camera_opener_ui import CameraOpenerUi
from .room_opener.ui_tabs.room_opener_ui import RoomOpenerUi
from .foreground import ForegroundTracker
from .ui_tabs.tray_ui import TrayUi
from .ui_tabs.settings_menu_ui import SettingsMenuUi
from .shutdown_coordinator import ShutdownCoordinator
from paltalk_automation.advert_blocker.ui_tabs.advert_blocker_tab import AdvertBlockerTab
from paltalk_automation.admin_actions.ui_tabs.admin_actions_tab import AdminActionsTab
from paltalk_automation.mic_timer.ui_tabs.mic_timer_tab import MicTimerTab
from paltalk_automation.room_opener.ui_tabs.room_opener_tab import RoomOpenerTab
from .styles import APP_STYLE
from .paltalk_startup_coordinator import PaltalkStartupCoordinator



class MainWindow(CameraOpenerUi, RoomOpenerUi, SettingsMenuUi, TrayUi, QMainWindow):

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
        self.initialize_camera_state()
        self._closing_pending = False
        self.shutdown_coordinator = ShutdownCoordinator(self)
        self._quitting = False
        self.tray_icon = None
        self.foreground_tracker = ForegroundTracker()
        self.paltalk_was_running = False
        self.paltalk_startup = PaltalkStartupCoordinator(self)
        self.setStyleSheet(APP_STYLE)

        tabs = QTabWidget()
        self.create_settings_menu(tabs)
        self.room_opener_tab = RoomOpenerTab(self)
        self.bind_room_widgets()
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













