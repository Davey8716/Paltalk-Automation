import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from paltalk_automation import windows_startup
from paltalk_automation.ui_tabs.settings_menu_ui import SettingsMenuUi


class MenuWindow(SettingsMenuUi, QWidget):
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        self.create_settings_menu(self.tabs)


class WindowsStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_registry_detection(self):
        with patch.object(windows_startup.winreg, 'OpenKey') as open_key, \
             patch.object(windows_startup.winreg, 'QueryValueEx') as query:
            self.assertTrue(windows_startup.startup_enabled())
            query.assert_called_once_with(open_key.return_value.__enter__.return_value, 'Paltalk Automation')
            query.side_effect = FileNotFoundError
            self.assertFalse(windows_startup.startup_enabled())
            query.side_effect = PermissionError('denied')
            with self.assertRaises(PermissionError):
                windows_startup.startup_enabled()

    def test_enable_frozen_and_python_commands(self):
        executable = str(Path('C:/Program Files/Paltalk App/app.exe'))
        for frozen in (True, False):
            with self.subTest(frozen=frozen), \
                 patch.object(sys, 'frozen', frozen, create=True), \
                 patch.object(sys, 'executable', executable), \
                 patch.object(Path, 'exists', return_value=True), \
                 patch.object(windows_startup.winreg, 'CreateKey'), \
                 patch.object(windows_startup.winreg, 'SetValueEx') as write:
                windows_startup.set_startup(True)
                command = [executable] if frozen else [str(Path(executable).with_name('pythonw.exe')),
                    str(Path(windows_startup.__file__).resolve().parent.parent / 'main.py')]
                self.assertEqual(write.call_args.args[1:],
                                 ('Paltalk Automation', 0, windows_startup.winreg.REG_SZ,
                                  subprocess.list2cmdline(command)))

    def test_disable_and_missing_entry(self):
        with patch.object(windows_startup.winreg, 'OpenKey'), \
             patch.object(windows_startup.winreg, 'DeleteValue') as delete:
            windows_startup.set_startup(False)
            delete.assert_called_once()
            delete.side_effect = FileNotFoundError
            windows_startup.set_startup(False)

    def test_menu_initializes_and_changes_independently(self):
        with patch.object(windows_startup, 'startup_enabled', return_value=True), \
             patch.object(windows_startup, 'set_startup') as save:
            window = MenuWindow()
            self.assertTrue(window.start_with_windows.isChecked())
            window.start_with_windows.setChecked(False)
            save.assert_called_once_with(False)
            self.assertFalse(window.start_in_tray.isChecked())
            window.close()

    def test_menu_read_and_write_failures(self):
        with patch.object(windows_startup, 'startup_enabled', side_effect=PermissionError('denied')), \
             patch('paltalk_automation.ui_tabs.settings_menu_ui.QMessageBox.warning') as warning:
            window = MenuWindow()
            self.assertFalse(window.start_with_windows.isEnabled())
            warning.assert_called_once()
            window.close()
        with patch.object(windows_startup, 'startup_enabled', return_value=False), \
             patch.object(windows_startup, 'set_startup', side_effect=OSError('denied')), \
             patch('paltalk_automation.ui_tabs.settings_menu_ui.QMessageBox.warning') as warning:
            window = MenuWindow()
            window.start_with_windows.setChecked(True)
            self.assertFalse(window.start_with_windows.isChecked())
            warning.assert_called_once()
            window.close()


if __name__ == '__main__':
    unittest.main()
