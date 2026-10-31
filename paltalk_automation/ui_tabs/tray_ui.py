"""System tray interface and actions."""

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QStyle, QSystemTrayIcon


class TrayUi:
    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon_path = Path(__file__).resolve().parent.parent.parent / 'Icons' / 'Paltalk Automation.ico'
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
        camera_action = menu.addAction('Start camera monitoring')
        def update_camera_action():
            if self.camera_stop.isEnabled():
                camera_action.setText('Stop camera monitoring')
                camera_action.setEnabled(True)
            else:
                camera_action.setText('Start camera monitoring')
                camera_action.setEnabled(self.camera_start.isEnabled())
        def toggle_camera_monitoring():
            if self.camera_stop.isEnabled():
                self.camera_stop.click()
            elif self.camera_start.isEnabled():
                self.camera_start.click()
        camera_action.triggered.connect(toggle_camera_monitoring)
        menu.aboutToShow.connect(update_camera_action)
        update_camera_action()
        startup_action = menu.addAction('Start with Windows')
        startup_action.setCheckable(True)
        def sync_startup_action():
            startup_action.setChecked(self.start_with_windows.isChecked())
            startup_action.setEnabled(self.start_with_windows.isEnabled())
        def toggle_startup(enabled):
            self.start_with_windows.setChecked(enabled)
            sync_startup_action()
        startup_action.triggered.connect(toggle_startup)
        self.start_with_windows.toggled.connect(lambda _: sync_startup_action())
        menu.aboutToShow.connect(sync_startup_action)
        sync_startup_action()
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

