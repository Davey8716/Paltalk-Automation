import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from paltalk_room_opener.main_window import MainWindow


class RoomHighlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.fields = [QLineEdit('Alpha'), QLineEdit('Beta'), QLineEdit('Alpha')]
        self.buttons = [QPushButton() for _ in self.fields]
        self.window = SimpleNamespace(
            rooms=self.fields, open_room_buttons=self.buttons, room_states={},
            worker=None, close_room_worker=None,
            close_all_button=QPushButton(),
            set_button_enabled=MainWindow.set_button_enabled,
        )

    def update(self, states):
        self.window.room_states = states
        MainWindow.update_room_buttons(self.window)

    def test_highlights_follow_detected_state_and_names(self):
        self.update({'Alpha': True, 'Beta': False})
        self.assertEqual([field.property('roomOpen') for field in self.fields], [True, False, True])
        self.assertEqual([button.text() for button in self.buttons], ['Close', 'Open', 'Close'])
        self.fields[0].setText('Gamma')
        self.update({'Alpha': True, 'Beta': False})
        self.assertFalse(self.fields[0].property('roomOpen'))
        self.update({'Alpha': False, 'Gamma': True})
        self.assertEqual([field.property('roomOpen') for field in self.fields], [True, False, False])
        self.update(None)
        self.assertTrue(all(not field.property('roomOpen') for field in self.fields))

    def test_updates_during_opening_and_keeps_buttons_disabled(self):
        self.window.worker = object()
        self.update({'Alpha': True, 'Beta': False})
        self.assertTrue(self.fields[0].property('roomOpen'))
        self.assertFalse(any(button.isEnabled() for button in self.buttons))
        self.update({'Alpha': True, 'Beta': True})
        self.assertTrue(self.fields[1].property('roomOpen'))

    def test_room_buttons_follow_mode_availability(self):
        self.window.rooms = [QLineEdit(f'Room {i}') for i in range(1, 6)]
        self.window.open_room_buttons = [QPushButton() for _ in self.window.rooms]
        for field in self.window.rooms[3:]:
            field.setProperty('roomAvailable', False)
        MainWindow.update_room_buttons(self.window)
        self.assertEqual([button.isEnabled() for button in self.window.open_room_buttons],
                         [True, True, True, False, False])
        for field in self.window.rooms[3:]:
            field.setProperty('roomAvailable', True)
        MainWindow.update_room_buttons(self.window)
        self.assertTrue(all(button.isEnabled() for button in self.window.open_room_buttons))

    def test_other_room_close_does_not_flash_configured_buttons(self):
        self.window.close_room_worker = object()
        self.window.closing_other_room = 'Other'
        self.window.other_open_names = ['Other']
        self.update({'Alpha': False, 'Beta': False})
        self.assertTrue(all(button.isEnabled() for button in self.buttons))
        self.assertTrue(self.window.close_all_button.isEnabled())

    def test_close_all_requires_a_detected_open_configured_room(self):
        for states in (None, {}, {'Alpha': False, 'Beta': False}, {'Other': True}):
            self.update(states)
            self.assertFalse(self.window.close_all_button.isEnabled())
        self.update({'Alpha': True})
        self.assertTrue(self.window.close_all_button.isEnabled())
        self.fields[0].setText('Gamma')
        self.fields[2].setText('Gamma')
        self.update({'Alpha': True})
        self.assertFalse(self.window.close_all_button.isEnabled())
        self.update({'Beta': True})
        self.window.close_room_worker = object()
        MainWindow.update_room_buttons(self.window)
        self.assertFalse(self.window.close_all_button.isEnabled())

    def test_unavailable_scan_preserves_last_open_state(self):
        self.update({'Alpha': True, 'Beta': False})
        self.window.update_room_buttons = lambda: MainWindow.update_room_buttons(self.window)
        MainWindow.room_states_received(self.window, None)
        self.assertTrue(self.fields[0].property('roomOpen'))
        self.assertEqual(self.buttons[0].text(), 'Close')

    def test_toggle_always_checks_current_state(self):
        window = SimpleNamespace(rooms=self.fields, room_states={'Alpha': True},
                                 open_configured_room=MagicMock(), close_configured_room=MagicMock())
        MainWindow.toggle_configured_room(window, 0)
        window.open_configured_room.assert_called_once_with(0)
        window.close_configured_room.assert_not_called()

    def test_unknown_state_allows_opening_named_rooms(self):
        self.fields[1].clear()
        self.update(None)
        self.assertEqual([button.text() for button in self.buttons], ['Open', 'Open', 'Open'])
        self.assertEqual([button.isEnabled() for button in self.buttons], [True, False, True])
        window = SimpleNamespace(rooms=self.fields, room_states=None,
                                 open_configured_room=MagicMock(), close_configured_room=MagicMock())
        MainWindow.toggle_configured_room(window, 0)
        window.open_configured_room.assert_called_once_with(0)
        window.close_configured_room.assert_not_called()

    def test_refresh_runs_during_bulk_opening(self):
        worker = MagicMock()
        window = SimpleNamespace(room_state_worker=None, _quitting=False, worker=object(),
                                 close_room_worker=None, rooms=self.fields,
                                 log=MagicMock(),
                                 room_states_received=lambda _: None,
                                 room_state_finished=lambda: None)
        with patch('paltalk_room_opener.main_window.RoomStateWorker', return_value=worker):
            MainWindow.refresh_room_states(window)
        worker.start.assert_called_once()

    def test_refresh_does_not_overlap_single_room_opening(self):
        window = SimpleNamespace(room_state_worker=None, _quitting=False,
                                 worker=SimpleNamespace(check_existing=True), close_room_worker=None)
        with patch('paltalk_room_opener.main_window.RoomStateWorker') as worker:
            MainWindow.refresh_room_states(window)
        worker.assert_not_called()

    def test_single_room_waits_for_existing_scan_to_stop(self):
        scan = MagicMock()
        room_worker = MagicMock()
        window = SimpleNamespace(
            worker=None, close_room_worker=None, room_state_worker=scan,
            save_current_settings=lambda: True, delay=SimpleNamespace(value=lambda: 5),
            auto_open_pending=False, auto_open_attempts_remaining=0,
            auto_open_handled_for_session=False, _pending_single_start=False,
            _quitting=False, start_button=MagicMock(), close_all_button=MagicMock(),
            open_room_buttons=[], set_button_enabled=MagicMock(), log=MagicMock(), finished=MagicMock(),
        )
        with patch('paltalk_room_opener.main_window.RoomWorker', return_value=room_worker):
            MainWindow.start_room_worker(window, ['Alpha'], False, 'room: Alpha', check_existing=True)
        scan.requestInterruption.assert_called_once()
        room_worker.start.assert_not_called()
        MainWindow.room_state_finished(window)
        room_worker.start.assert_called_once()

    def test_finished_restores_buttons_after_a_failed_single_room(self):
        window = SimpleNamespace(start_button=MagicMock(), worker=object(),
                                 update_room_buttons=MagicMock(), refresh_room_states=MagicMock())
        MainWindow.finished(window)
        window.start_button.setEnabled.assert_called_once_with(True)
        self.assertIsNone(window.worker)
        window.update_room_buttons.assert_called_once()
        window.refresh_room_states.assert_called_once()


if __name__ == '__main__':
    unittest.main()
