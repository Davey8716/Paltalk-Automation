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

    def test_refresh_runs_during_bulk_opening(self):
        worker = MagicMock()
        window = SimpleNamespace(room_state_worker=None, _quitting=False, worker=object(),
                                 close_room_worker=None, rooms=self.fields,
                                 room_states_received=lambda _: None,
                                 room_state_finished=lambda: None)
        with patch('paltalk_room_opener.main_window.RoomStateWorker', return_value=worker):
            MainWindow.refresh_room_states(window)
        worker.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
