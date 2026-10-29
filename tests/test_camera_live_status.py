import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QListWidget

from paltalk_room_opener.camera_name_list import LIVE_ROLE
from paltalk_room_opener.main_window import MainWindow


class CameraLiveStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_status_updates_without_changing_or_saving_names(self):
        names = QListWidget()
        names.addItems(['Alice', 'Bob'])
        changed = MagicMock()
        names.itemChanged.connect(changed)
        window = SimpleNamespace(camera_names=names)
        MainWindow.update_camera_live_status(window, ['alice'])
        self.assertTrue(names.item(0).data(LIVE_ROLE))
        self.assertFalse(bool(names.item(1).data(LIVE_ROLE)))
        self.assertEqual(names.item(0).text(), 'Alice')
        changed.assert_not_called()
        MainWindow.update_camera_live_status(window, [])
        self.assertFalse(names.item(0).data(LIVE_ROLE))
        changed.assert_not_called()

    def test_portrait_toggle_updates_watcher_and_saves(self):
        window = SimpleNamespace(camera_portrait_adjustment=MagicMock(), camera_worker=MagicMock(),
                                 save_camera_settings=MagicMock())
        MainWindow.camera_portrait_adjustment_changed(window, False)
        window.camera_portrait_adjustment.setText.assert_called_once_with('Portrait adjustment: Off')
        window.camera_worker.update_portrait_adjustment.assert_called_once_with(False)
        window.save_camera_settings.assert_called_once()
