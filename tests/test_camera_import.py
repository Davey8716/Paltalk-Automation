import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QListWidget

from paltalk_room_opener.main_window import MainWindow


class CameraImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, names):
        widget = QListWidget()
        widget.addItems(names)
        return SimpleNamespace(camera_names=widget, camera_next_order=len(names) + 1,
                               camera_alphabetical=SimpleNamespace(isChecked=lambda: False),
                               save_camera_settings=Mock(return_value=True), camera_worker=None,
                               remind_camera_export=Mock(), camera_log=Mock())

    def run_import(self, window, contents):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'names.txt'
            path.write_text(contents, encoding='utf-8')
            with patch('paltalk_room_opener.main_window.QFileDialog.getOpenFileName', return_value=(str(path), '')):
                MainWindow.import_camera_names(window)

    def test_imports_numbered_and_plain_names_skipping_duplicates(self):
        window = self.window(['Alice'])
        self.run_import(window, '1. ALICE\n2. Zoë\nBob\nzoë\n')
        self.assertEqual([window.camera_names.item(i).text() for i in range(3)], ['Alice', 'Zoë', 'Bob'])
        window.save_camera_settings.assert_called_once()

    def test_over_limit_adds_nothing(self):
        window = self.window([f'user{i}' for i in range(200)])
        with patch('paltalk_room_opener.main_window.QMessageBox.warning') as warning:
            self.run_import(window, 'New user\n')
        self.assertEqual(window.camera_names.count(), 200)
        warning.assert_called_once()
        window.save_camera_settings.assert_not_called()

    def test_save_failure_rolls_back(self):
        window = self.window(['Alice'])
        window.save_camera_settings.return_value = False
        self.run_import(window, 'Bob\n')
        self.assertEqual(window.camera_names.count(), 1)
        self.assertEqual(window.camera_next_order, 2)


if __name__ == '__main__':
    unittest.main()
