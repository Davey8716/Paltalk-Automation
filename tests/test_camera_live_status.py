import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QListWidget, QPlainTextEdit

from paltalk_automation.camera_opener.ui_tabs.camera_name_list import LIVE_ROLE
from paltalk_automation.main_window import MainWindow


class CameraLiveStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_finished_monitor_clears_all_logs(self):
        for restart in (False, True):
            window = SimpleNamespace(camera_prompts=MagicMock(), update_camera_live_status=MagicMock(),
                                     camera_worker=object(), camera_start=MagicMock(), camera_stop=MagicMock(),
                                     camera_log=MagicMock(), camera_invoked_log=MagicMock(),
                                     camera_failed_log=MagicMock(), camera_restart_pending=restart,
                                     start_cameras=MagicMock())
            window.clear_camera_log = lambda log: MainWindow.clear_camera_log(window, log)
            MainWindow.cameras_finished(window)
            for log in (window.camera_log, window.camera_invoked_log, window.camera_failed_log):
                self.assertEqual(log.clear.call_count, 0 if restart else 1)
            self.assertEqual(window.start_cameras.call_count, int(restart))

    def test_stopped_message_is_red_and_only_shown_when_off(self):
        log = QPlainTextEdit()
        window = SimpleNamespace(camera_worker=None)
        MainWindow.clear_camera_log(window, log)
        self.assertEqual(log.toPlainText(), 'Camera monitoring stopped.')
        self.assertEqual(log.document().firstBlock().begin().fragment().charFormat().foreground().color().name(), '#e5484d')
        window.camera_worker = object()
        MainWindow.clear_camera_log(window, log)
        self.assertEqual(log.toPlainText(), '')

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
