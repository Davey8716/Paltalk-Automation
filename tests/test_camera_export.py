import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QListWidget
from PySide6.QtCore import Qt

from paltalk_room_opener.main_window import MainWindow


class CameraExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, names):
        widget = QListWidget()
        widget.addItems(names)
        return SimpleNamespace(camera_names=widget, clear_camera_export_reminder=Mock())

    def test_exports_displayed_order_and_unicode(self):
        for names in (['Zoë', 'Alice'], ['Alice', 'Zoë']):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'names.txt'
                with patch('paltalk_room_opener.main_window.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                    MainWindow.export_camera_names(self.window(names))
                self.assertEqual(path.read_text(encoding='utf-8'),
                                 f'1. {names[0]}\n2. {names[1]}\n')

    def test_empty_list_shows_message_without_opening_dialog(self):
        with patch('paltalk_room_opener.main_window.QMessageBox.information') as message, \
             patch('paltalk_room_opener.main_window.QFileDialog.getSaveFileName') as dialog:
            MainWindow.export_camera_names(self.window([]))
        message.assert_called_once()
        dialog.assert_not_called()

    def test_export_keeps_assigned_numbers_in_display_order(self):
        window = self.window(['Alice', 'Zoë'])
        window.camera_names.item(0).setData(Qt.ItemDataRole.UserRole, 2)
        window.camera_names.item(1).setData(Qt.ItemDataRole.UserRole, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'names.txt'
            with patch('paltalk_room_opener.main_window.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                MainWindow.export_camera_names(window)
            self.assertEqual(path.read_text(encoding='utf-8'), '2. Alice\n1. Zoë\n')

    def test_cancel_does_not_write(self):
        window = self.window(['Alice'])
        with patch('paltalk_room_opener.main_window.QFileDialog.getSaveFileName', return_value=('', '')), \
             patch('pathlib.Path.write_text') as write:
            MainWindow.export_camera_names(window)
        write.assert_not_called()
        window.clear_camera_export_reminder.assert_not_called()

    def test_success_clears_reminder(self):
        window = self.window(['Alice'])
        with tempfile.TemporaryDirectory() as directory, \
             patch('paltalk_room_opener.main_window.QFileDialog.getSaveFileName',
                   return_value=(str(Path(directory) / 'names.txt'), '')):
            MainWindow.export_camera_names(window)
        window.clear_camera_export_reminder.assert_called_once()

    def test_write_error_shows_warning(self):
        window = self.window(['Alice'])
        with patch('paltalk_room_opener.main_window.QFileDialog.getSaveFileName', return_value=('names.txt', '')), \
             patch('pathlib.Path.write_text', side_effect=OSError('access denied')), \
             patch('paltalk_room_opener.main_window.QMessageBox.warning') as warning:
            MainWindow.export_camera_names(window)
        self.assertIn('access denied', warning.call_args.args[2])
        window.clear_camera_export_reminder.assert_not_called()


if __name__ == '__main__':
    unittest.main()
