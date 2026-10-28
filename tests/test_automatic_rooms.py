import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from paltalk_room_opener.main_window import MainWindow
from paltalk_room_opener.worker import RoomWorker


class AutomaticRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def run_worker(self, states, automatic=True):
        worker = RoomWorker(['Alpha', 'Beta'], 5, automatic=automatic)
        results, messages = [], []
        worker.completed.connect(results.append)
        worker.message.connect(messages.append)
        with patch('paltalk_room_opener.worker.restore_paltalk') as restore, \
             patch('paltalk_room_opener.worker.room_states', side_effect=states) as check, \
             patch('paltalk_room_opener.worker.open_rooms', return_value=1) as open_rooms:
            worker.run()
        restore.assert_called_once()
        return results, messages, check, open_rooms

    def test_all_open_skips_tiles_and_finishes(self):
        results, messages, _, opener = self.run_worker([{'Alpha': True, 'Beta': True}])
        self.assertEqual(results, [RoomWorker.ALREADY_OPEN])
        self.assertIn('All configured rooms are already open.', messages)
        opener.assert_not_called()
        window = self.window()
        with patch('paltalk_room_opener.main_window.QTimer.singleShot') as timer:
            MainWindow.automatic_open_finished(window, results[0])
        timer.assert_not_called()
        self.assertTrue(window.auto_open_handled_for_session)

    def test_only_closed_rooms_are_opened(self):
        results, messages, _, opener = self.run_worker([{'Alpha': True, 'Beta': False}])
        self.assertEqual(results, [1])
        self.assertEqual(opener.call_args.args[0], ['Beta'])
        self.assertIn('Already open, skipping room: Alpha', messages)

    def test_unavailable_and_ambiguous_states_do_not_open_rooms(self):
        for state in (None, {'Alpha': False}, RuntimeError('unavailable')):
            with self.subTest(state=state):
                results, _, _, opener = self.run_worker([state])
                self.assertEqual(results, [RoomWorker.STATE_UNAVAILABLE])
                opener.assert_not_called()
                window = self.window()
                with patch('paltalk_room_opener.main_window.QTimer.singleShot') as timer:
                    MainWindow.automatic_open_finished(window, results[0])
                timer.assert_called_once()

    def test_retry_checks_state_again(self):
        worker = RoomWorker(['Alpha', 'Beta'], 5, automatic=True)
        results = []
        worker.completed.connect(results.append)
        with patch('paltalk_room_opener.worker.restore_paltalk'), \
             patch('paltalk_room_opener.worker.room_states', side_effect=[None, {'Alpha': True, 'Beta': False}]) as check, \
             patch('paltalk_room_opener.worker.open_rooms', return_value=1) as opener:
            worker.run()
            worker.run()
        self.assertEqual(check.call_count, 2)
        self.assertEqual(results, [RoomWorker.STATE_UNAVAILABLE, 1])
        self.assertEqual(opener.call_args.args[0], ['Beta'])

    def test_manual_open_does_not_check_state(self):
        _, _, check, opener = self.run_worker([], automatic=False)
        check.assert_not_called()
        self.assertEqual(opener.call_args.args[0], ['Alpha', 'Beta'])

    def test_restore_precedes_room_operations(self):
        for automatic in (False, True):
            events = []
            worker = RoomWorker(['Alpha'], 5, automatic=automatic)
            with patch('paltalk_room_opener.worker.restore_paltalk', side_effect=lambda: events.append('restore')), \
                 patch('paltalk_room_opener.worker.room_states', side_effect=lambda names: events.append('check') or {'Alpha': False}), \
                 patch('paltalk_room_opener.worker.open_rooms', side_effect=lambda *args: events.append('open') or 1):
                worker.run()
            self.assertEqual(events, ['restore', 'check', 'open'] if automatic else ['restore', 'open'])

    def test_restore_failure_prevents_opening(self):
        for automatic in (False, True):
            with self.subTest(automatic=automatic):
                worker = RoomWorker(['Alpha'], 5, automatic=automatic)
                messages, results = [], []
                worker.message.connect(messages.append)
                worker.completed.connect(results.append)
                with patch('paltalk_room_opener.worker.restore_paltalk', side_effect=RuntimeError('window unavailable')), \
                     patch('paltalk_room_opener.worker.room_states') as states, \
                     patch('paltalk_room_opener.worker.open_rooms') as opener:
                    worker.run()
                states.assert_not_called()
                opener.assert_not_called()
                self.assertEqual(results, [RoomWorker.STATE_UNAVAILABLE if automatic else -1])
                self.assertIn('window unavailable', messages[0])

    def window(self):
        return SimpleNamespace(auto_open_pending=True, auto_open_attempts_remaining=2,
                               auto_open_handled_for_session=False, AUTO_OPEN_MAX_ATTEMPTS=6,
                               AUTO_OPEN_DELAY_MS=5000, auto_open_button=SimpleNamespace(isChecked=lambda: True),
                               log=MagicMock(), start_automatically=MagicMock())


if __name__ == '__main__':
    unittest.main()
