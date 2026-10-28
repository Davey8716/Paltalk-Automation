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
        return SimpleNamespace(camera_names=widget, clear_camera_export_reminder=Mock(),
                               remind_camera_export=Mock())

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

    def test_deleting_middle_name_renumbers_in_original_order(self):
        window = self.window(['Charlie', 'Alice', 'Bob'])
        for i, number in enumerate((3, 1, 2)):
            window.camera_names.item(i).setData(Qt.ItemDataRole.UserRole, number)
        window.camera_next_order = 4
        window.camera_worker = None
        window.save_camera_settings = Mock(return_value=True)
        window.renumber_camera_names = lambda: MainWindow.renumber_camera_names(window)
        MainWindow.delete_camera_name(window, window.camera_names.item(2))
        self.assertEqual([window.camera_names.item(i).data(Qt.ItemDataRole.UserRole)
                          for i in range(2)], [2, 1])
        self.assertEqual(window.camera_next_order, 3)
        window.save_camera_settings.assert_called_once()
        window.remind_camera_export.assert_called_once_with('red')

    def test_failed_deletion_restores_numbers(self):
        window = self.window(['Alice', 'Bob', 'Charlie'])
        for i in range(3):
            window.camera_names.item(i).setData(Qt.ItemDataRole.UserRole, i + 1)
        window.camera_next_order = 4
        window.camera_worker = None
        window.save_camera_settings = Mock(return_value=False)
        window.renumber_camera_names = lambda: MainWindow.renumber_camera_names(window)
        MainWindow.delete_camera_name(window, window.camera_names.item(1))
        self.assertEqual([window.camera_names.item(i).data(Qt.ItemDataRole.UserRole)
                          for i in range(3)], [1, 2, 3])
        self.assertEqual(window.camera_next_order, 4)
        window.remind_camera_export.assert_not_called()

    def test_bulk_deletion_and_failed_save_restore_display_order(self):
        for saved in (True, False):
            with self.subTest(saved=saved):
                window = self.window(['Charlie', 'Alice', 'Bob', 'Dave'])
                for i, number in enumerate((3, 1, 2, 4)):
                    window.camera_names.item(i).setData(Qt.ItemDataRole.UserRole, number)
                window.camera_next_order = 5
                window.camera_worker = None
                window.save_camera_settings = Mock(return_value=saved)
                window.renumber_camera_names = lambda: MainWindow.renumber_camera_names(window)
                MainWindow.delete_camera_names(window, [window.camera_names.item(0), window.camera_names.item(2)])
                expected = ['Alice', 'Dave'] if saved else ['Charlie', 'Alice', 'Bob', 'Dave']
                self.assertEqual([window.camera_names.item(i).text() for i in range(window.camera_names.count())], expected)
                numbers = [window.camera_names.item(i).data(Qt.ItemDataRole.UserRole)
                           for i in range(window.camera_names.count())]
                self.assertEqual(numbers, [1, 2] if saved else [3, 1, 2, 4])
                window.save_camera_settings.assert_called_once()


if __name__ == '__main__':
    unittest.main()
