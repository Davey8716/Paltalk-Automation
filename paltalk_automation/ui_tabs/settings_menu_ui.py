"""Application settings menu."""

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QMessageBox, QToolButton

from paltalk_automation import settings


class SettingsMenuUi:
    def create_settings_menu(self, tabs):
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

    def open_settings_folder(self):
        try:
            settings.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(settings.APP_DATA_DIR))):
                raise OSError('Windows could not open the folder.')
        except OSError as exc:
            QMessageBox.warning(self, 'Settings folder', f'Could not open settings folder: {exc}')

