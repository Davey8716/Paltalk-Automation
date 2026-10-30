import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QListWidget
from PySide6.QtCore import QMimeData, QUrl

from paltalk_automation.camera_opener.ui_tabs.text_import_button import TextImportButton
from paltalk_automation.main_window import MainWindow


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
            with patch('paltalk_automation.camera_opener.ui_tabs.camera_opener_ui.QFileDialog.getOpenFileName', return_value=(str(path), '')):
                MainWindow.import_camera_names(window)

    def test_imports_numbered_and_plain_names_skipping_duplicates(self):
        window = self.window(['Alice'])
        self.run_import(window, '1. ALICE\n2. Zoë\nBob\nzoë\n')
        self.assertEqual([window.camera_names.item(i).text() for i in range(3)], ['Alice', 'Zoë', 'Bob'])
        window.save_camera_settings.assert_called_once()

    def test_over_limit_adds_nothing(self):
        window = self.window([f'user{i}' for i in range(200)])
        with patch('paltalk_automation.camera_opener.ui_tabs.camera_opener_ui.QMessageBox.warning') as warning:
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

    def test_text_file_drop_imports_and_rejects_other_files(self):
        window = self.window(['Alice'])
        button = TextImportButton('Import text')
        button.fileDropped.connect(lambda path: MainWindow.import_camera_file(window, path))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'names.txt'
            path.write_text('Alice\nBob\n', encoding='utf-8')
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            event = Mock()
            event.mimeData.return_value = mime
            button.dragEnterEvent(event)
            button.dropEvent(event)
            self.assertEqual(window.camera_names.item(1).text(), 'Bob')
            event.acceptProposedAction.assert_called()
            mime.setUrls([QUrl.fromLocalFile(str(Path(directory) / 'other.png'))])
            event.reset_mock()
            button.dragEnterEvent(event)
            button.dropEvent(event)
            event.acceptProposedAction.assert_not_called()
            self.assertEqual(window.camera_names.count(), 2)


if __name__ == '__main__':
    unittest.main()
