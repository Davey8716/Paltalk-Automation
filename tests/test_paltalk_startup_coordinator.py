import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from paltalk_automation.paltalk_startup_coordinator import PaltalkStartupCoordinator


class PaltalkStartupCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.window = Mock()
        self.window._quitting = False
        self.window.paltalk_was_running = False
        self.window.camera_auto_handled = False
        self.window.camera_worker = None
        self.window.camera_auto.isChecked.return_value = True
        timer_patch = patch('paltalk_automation.paltalk_startup_coordinator.QTimer')
        timer_patch.start()
        self.addCleanup(timer_patch.stop)
        self.coordinator = PaltalkStartupCoordinator(self.window)

    def test_session_detection_starts_camera_once_and_resets_on_stop(self):
        self.coordinator.process_received(True)
        self.coordinator.process_received(True)
        self.window.start_cameras.assert_called_once_with(automatic=True)
        self.assertTrue(self.window.paltalk_was_running)
        self.assertEqual(self.window.room_paltalk_running.call_count, 2)
        self.coordinator.process_received(False)
        self.assertFalse(self.window.paltalk_was_running)
        self.assertFalse(self.window.camera_auto_handled)
        self.window.room_paltalk_stopped.assert_called_once()
        self.coordinator.process_received(True)
        self.assertEqual(self.window.start_cameras.call_count, 2)

    @patch('paltalk_automation.paltalk_startup_coordinator.PaltalkProcessWorker')
    def test_one_worker_at_a_time_and_none_while_quitting(self, factory):
        worker = factory.return_value
        self.coordinator.check()
        self.coordinator.check()
        factory.assert_called_once()
        worker.start.assert_called_once()
        self.coordinator.process_finished()
        self.window._quitting = True
        self.coordinator.check()
        factory.assert_called_once()
        self.coordinator.process_received(True)
        self.window.start_cameras.assert_not_called()


if __name__ == '__main__':
    unittest.main()
