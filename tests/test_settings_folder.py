import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from paltalk_automation import settings
from paltalk_automation.main_window import MainWindow


class SettingsFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_creates_and_opens_settings_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'settings'
            with patch.object(settings, 'APP_DATA_DIR', folder), \
                 patch('paltalk_automation.ui_tabs.settings_menu_ui.QDesktopServices.openUrl', return_value=True) as opener:
                MainWindow.open_settings_folder(None)
            self.assertTrue(folder.is_dir())
            self.assertEqual(Path(opener.call_args.args[0].toLocalFile()), folder)

    def test_open_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(settings, 'APP_DATA_DIR', Path(temp)), \
             patch('paltalk_automation.ui_tabs.settings_menu_ui.QDesktopServices.openUrl', return_value=False), \
             patch('paltalk_automation.ui_tabs.settings_menu_ui.QMessageBox.warning') as warning:
            MainWindow.open_settings_folder(None)
        warning.assert_called_once()


if __name__ == '__main__':
    unittest.main()
