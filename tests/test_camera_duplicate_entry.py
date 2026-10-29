import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QListWidget

from paltalk_room_opener.main_window import CameraEntryField, MainWindow


class CameraDuplicateEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.entry = CameraEntryField()
        self.names = QListWidget()
        self.window = SimpleNamespace(camera_entry=self.entry, camera_names=self.names)
        update = lambda *args: MainWindow.update_camera_duplicate(self.window, *args)
        self.entry.textChanged.connect(update)
        self.names.model().rowsInserted.connect(update)
        self.names.model().rowsRemoved.connect(update)
        self.names.model().dataChanged.connect(update)

    def test_duplicate_and_correction(self):
        self.names.addItem('Alice')
        for text in ('Alice', '  aLIce  '):
            self.entry.setText(text)
            self.assertTrue(self.entry.property('roomDuplicate'))
            self.assertFalse(self.entry.duplicate_message.isHidden())
            self.assertEqual(self.entry.text(), text)
        for text in ('Alicia', ''):
            self.entry.setText(text)
            self.assertFalse(self.entry.property('roomDuplicate'))
            self.assertTrue(self.entry.duplicate_message.isHidden())

    def test_list_changes_refresh_feedback(self):
        self.entry.setText('Alice')
        self.names.addItem('Alice')
        self.assertTrue(self.entry.property('roomDuplicate'))
        self.names.item(0).setText('Bob')
        self.assertFalse(self.entry.property('roomDuplicate'))
        self.names.item(0).setText('Alice')
        self.assertTrue(self.entry.property('roomDuplicate'))
        self.names.takeItem(0)
        self.assertFalse(self.entry.property('roomDuplicate'))

    def test_duplicate_add_is_rejected(self):
        self.names.addItem('Alice')
        self.entry.setText(' alice ')
        window = SimpleNamespace(camera_entry=self.entry, camera_names=self.names,
                                 camera_username_list=lambda: ['Alice'], update_camera_names=MagicMock())
        MainWindow.add_camera_name(window)
        self.assertEqual(self.names.count(), 1)
        self.assertEqual(self.entry.text(), ' alice ')
        window.update_camera_names.assert_not_called()


if __name__ == '__main__':
    unittest.main()
