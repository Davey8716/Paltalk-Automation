import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from paltalk_room_opener.main_window import MainWindow


class RoomMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.window = SimpleNamespace(
            monitor_rooms=MagicMock(), reopen_rooms=MagicMock(), monitor_states={},
            monitor_reopen_pending=set(), selected_room_names=lambda: ['Alpha', 'Beta'],
            log=MagicMock(), tray_icon=MagicMock(), worker=None, close_room_worker=None,
            start_room_worker=MagicMock(),
        )
        self.window.monitor_rooms.isChecked.return_value = True
        self.window.reopen_rooms.isChecked.return_value = True

    def scan(self, states):
        MainWindow.process_room_monitor(self.window, states)

    def test_closure_alerts_once_and_requests_safe_reopen(self):
        self.scan({'Alpha': True, 'Beta': False})
        self.scan(None)
        self.scan({'Alpha': False, 'Beta': False})
        self.scan({'Alpha': False, 'Beta': False})
        self.window.tray_icon.showMessage.assert_called_once()
        self.window.start_room_worker.assert_called_once_with(
            ['Alpha'], True, 'reopening monitored rooms', monitoring=True)

    def test_unknown_and_initially_closed_do_not_alert(self):
        self.scan({'Alpha': True, 'Beta': False})
        self.scan({'Beta': False})
        self.window.tray_icon.showMessage.assert_not_called()
        self.window.start_room_worker.assert_not_called()

    def test_busy_reopen_waits_for_next_scan(self):
        self.scan({'Alpha': True})
        self.window.worker = object()
        self.scan({'Alpha': False})
        self.window.start_room_worker.assert_not_called()
        self.window.worker = None
        self.scan({'Alpha': False})
        self.window.start_room_worker.assert_called_once()

    def test_alert_only_does_not_reopen(self):
        self.window.reopen_rooms.isChecked.return_value = False
        self.scan({'Alpha': True})
        self.scan({'Alpha': False})
        self.window.tray_icon.showMessage.assert_called_once()
        self.window.start_room_worker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
