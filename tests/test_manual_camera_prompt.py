import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from paltalk_automation import settings
from paltalk_automation.camera_opener.backend.camera_automation import ManualCameraTracker
from paltalk_automation.main_window import MainWindow
from paltalk_automation.camera_opener.ui_tabs.manual_camera_prompt import ManualCameraPromptController
from paltalk_automation.camera_opener.backend.camera_worker import CameraWorker


def row(name, state):
    return (name if isinstance(name, tuple) else (name,), state, None, 1, 'On Cam')


class ManualTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = ManualCameraTracker()

    def scan(self, rows, room=1, enabled=True, generation=0, names=()):
        return self.tracker.scan(rows, room, enabled, generation, names)

    def test_baseline_transitions_and_reopening(self):
        self.assertEqual(self.scan([row('Alice', 'open')]), [])
        self.assertEqual(self.scan([row('Alice', 'open')]), [])
        self.assertEqual(self.scan([row('Alice', 'available')]), [])
        self.assertEqual(self.scan([row('Alice', 'open')]), ['Alice'])
        self.assertEqual(self.scan([row('Alice', 'open')]), [])
        self.scan([row('Alice', 'available')])
        self.assertEqual(self.scan([row('Alice', 'open')]), ['Alice'])

    def test_rebaseline_on_room_toggle_and_loss_of_reading(self):
        self.scan([row('Alice', 'available')])
        self.assertEqual(self.scan([row('Alice', 'open')], room=2), [])
        self.scan([row('Alice', 'available')], room=2)
        self.assertEqual(self.scan([row('Alice', 'open')], room=2, generation=1), [])
        self.scan([row('Alice', 'available')], enabled=False)
        self.assertEqual(self.scan([row('Alice', 'open')]), [])
        self.scan([row('Alice', 'available')])
        self.scan([])
        self.assertEqual(self.scan([row('Alice', 'open')]), [])

    def test_ambiguous_and_listed_names_are_not_prompted(self):
        self.scan([row(('Alice', 'Alicc'), 'available'), row('Bob', 'available')])
        self.assertEqual(self.scan([row('Alice', 'open'), row('Bob', 'open')], names=['bob']), ['Alice'])
        self.scan([row('Alice', 'available'), row('Alice', 'available')])
        self.assertEqual(self.scan([row('Alice', 'open')]), [])

    def test_disagreeing_ocr_passes_can_identify_same_opened_row(self):
        self.scan([row(('aizasam', 'aiz asam'), 'available')])
        self.assertEqual(self.scan([row(('aizasam', 'aizasarn'), 'open')]), ['aizasam'])

    def test_shared_ocr_candidates_between_rows_are_ambiguous(self):
        self.scan([row(('aizasam', 'aizasarn'), 'available'), row('aizasarn', 'available')])
        self.assertEqual(self.scan([row(('aizasam', 'aizasarn'), 'open')]), [])
        self.scan([row('aizasam', 'available')])
        self.assertEqual(self.scan([row('aizasam', 'open'), row('aizasam', 'open')]), [])

    def test_same_user_in_mic_queue_and_on_cam_prompts_once(self):
        def section_row(section, state):
            return (('JinTonic_', 'JinTonic'), state, None, 10, section)
        self.scan([section_row('Mic Queue', 'available'), section_row('On Cam', 'available')])
        self.assertEqual(self.scan([section_row('Mic Queue', 'open'), section_row('On Cam', 'open')]), ['JinTonic_'])
        self.assertEqual(self.scan([section_row('Mic Queue', 'open'), section_row('On Cam', 'open')]), [])

    def test_mic_queue_manual_camera_is_detected(self):
        self.scan([(('JinTonic_',), 'available', None, 10, 'Mic Queue')])
        self.assertEqual(self.scan([(('JinTonic_',), 'open', None, 10, 'Mic Queue')]), ['JinTonic_'])

    def test_setting_round_trip_and_worker_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', root), patch.object(settings, 'CAMERA_SETTINGS_PATH', root / 'camera.json'):
                self.assertEqual(settings.load_camera_settings(), {})
                settings.save_camera_settings([], False, manual_camera_prompt=True)
                self.assertTrue(settings.load_camera_settings()['manual_camera_prompt'])
        worker = CameraWorker([], manual_prompt=False)
        worker.update_manual_prompt(True)
        self.assertTrue(worker.manual_prompt)
        self.assertEqual(worker.name_updates.get_nowait(), {'manual_prompt': True})


class PromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QWidget()
        w = self.window
        w.camera_worker = SimpleNamespace(isInterruptionRequested=lambda: False)
        w.camera_manual_prompt = SimpleNamespace(isChecked=lambda: True)
        w.camera_prompts = ManualCameraPromptController(w)
        w.camera_username_list = lambda: []
        w.add_camera_username = Mock()

    def tearDown(self):
        self.window.camera_prompts.clear()
        self.window.close()

    def test_accept_and_decline(self):
        w = self.window
        w.camera_prompts.queue('Alice')
        w.camera_prompts.dialog.setTextValue('aizasam')
        w.camera_prompts.dialog.done(QDialog.DialogCode.Accepted)
        w.add_camera_username.assert_called_once_with('aizasam')
        w.camera_prompts.queue('Bob')
        w.camera_prompts.dialog.done(QDialog.DialogCode.Rejected)
        w.add_camera_username.assert_called_once()

    def test_cancel_clears_pending_and_listed_names_are_skipped(self):
        w = self.window
        w.camera_username_list = lambda: ['Alice']
        w.camera_prompts.queue('alice')
        self.assertIsNone(w.camera_prompts.dialog)
        w.camera_prompts.queue('Bob')
        w.camera_prompts.queue('Carol')
        w.camera_prompts.clear()
        self.assertIsNone(w.camera_prompts.dialog)
        self.assertEqual(w.camera_prompts.queue_items, [])
        w.add_camera_username.assert_not_called()

    def test_capacity_and_duplicate_are_checked_before_adding(self):
        w = SimpleNamespace(camera_username_list=lambda: ['Alice'],
                            camera_names=SimpleNamespace(count=lambda: 200))
        with patch('paltalk_automation.camera_opener.ui_tabs.camera_opener_ui.QMessageBox.warning') as warning:
            MainWindow.add_camera_username(w, 'alice')
            warning.assert_not_called()
            MainWindow.add_camera_username(w, 'Bob')
            warning.assert_called_once()

    def test_empty_list_can_start_only_when_prompt_enabled(self):
        button = SimpleNamespace(isChecked=lambda: False)
        log = SimpleNamespace(appendPlainText=Mock())
        w = SimpleNamespace(camera_worker=None, camera_username_list=lambda: [],
                            camera_manual_prompt=button, camera_log=log,
                            save_camera_settings=Mock(return_value=True))
        MainWindow.start_cameras(w)
        w.save_camera_settings.assert_not_called()
        button.isChecked = lambda: True
        signal = SimpleNamespace(connect=Mock())
        worker = SimpleNamespace(message=signal, invoked=signal, failed=signal,
                                 live_status=signal, manual_opened=signal, finished=signal,
                                 start=Mock())
        w.camera_invoked_log = log
        w.camera_failed_log = log
        w.camera_portrait_adjustment = SimpleNamespace(isChecked=lambda: True)
        w.camera_start = SimpleNamespace(setEnabled=Mock())
        w.camera_stop = SimpleNamespace(setEnabled=Mock())
        w.update_camera_live_status = Mock()
        w.camera_prompts = SimpleNamespace(queue=Mock())
        w.cameras_finished = Mock()
        with patch('paltalk_automation.camera_opener.ui_tabs.camera_opener_ui.CameraWorker', return_value=worker) as factory:
            MainWindow.start_cameras(w)
        factory.assert_called_once_with([], True, True)
        worker.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
