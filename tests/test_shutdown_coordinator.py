import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from paltalk_automation.shutdown_coordinator import ShutdownCoordinator


class ShutdownCoordinatorTests(unittest.TestCase):
    def window(self):
        window = Mock()
        window._quitting = True
        window._closing_pending = False
        window.tray_icon = None
        window.mic_timer_tab = SimpleNamespace(mic_timer_worker=None)
        window.admin_actions_tab = SimpleNamespace(chat_reader_worker=None)
        for name in ('camera_worker', 'worker', 'close_room_worker', 'room_state_worker',
                     'recent_rooms_worker'):
            setattr(window, name, None)
        window.paltalk_startup = SimpleNamespace(worker=None)
        return window

    @patch('paltalk_automation.shutdown_coordinator.QTimer.singleShot')
    def test_interrupts_selected_workers_and_waits_for_all(self, schedule):
        window = self.window()
        window.worker = Mock()
        window.worker.isRunning.return_value = True
        window.room_state_worker = Mock()
        window.room_state_worker.isRunning.return_value = True
        coordinator = ShutdownCoordinator(window)
        event = Mock()
        coordinator.close_event(event)
        window.worker.requestInterruption.assert_called_once()
        window.room_state_worker.requestInterruption.assert_not_called()
        event.ignore.assert_called_once()
        self.assertTrue(window._closing_pending)
        schedule.assert_called_once_with(100, coordinator.finish_when_stopped)
        schedule.reset_mock()
        window.worker.isRunning.return_value = False
        coordinator.finish_when_stopped()
        schedule.assert_called_once_with(100, coordinator.finish_when_stopped)
        window.room_state_worker.isRunning.return_value = False
        coordinator.finish_when_stopped()
        window.close.assert_called_once()

    @patch('paltalk_automation.shutdown_coordinator.QTimer.singleShot')
    def test_completed_shutdown_and_tray_close(self, schedule):
        window = self.window()
        coordinator = ShutdownCoordinator(window)
        event = Mock()
        window._quitting = False
        window.tray_icon = Mock()
        coordinator.close_event(event)
        window.hide.assert_called_once()
        event.ignore.assert_called_once()
        window.advert_blocker_tab.advert_tracker.stop.assert_not_called()
        window._quitting = True
        coordinator.close_event(event)
        window.foreground_tracker.close.assert_called_once()
        window.tray_icon.hide.assert_called_once()
        event.accept.assert_called_once()
        self.assertEqual(schedule.call_args.args[0], 0)


if __name__ == '__main__':
    unittest.main()
