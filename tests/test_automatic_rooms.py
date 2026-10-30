import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from paltalk_automation.room_opener.backend.room_workers import RoomWorker
from paltalk_automation.room_opener.backend import room_helper_process


class AutomaticRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def run_helper(self, states, action='automatic'):
        events, messages = [], []
        with patch('sys.argv', ['helper', action, '["Alpha", "Beta"]', '7']), \
             patch.object(room_helper_process, 'send', side_effect=lambda kind, value: messages.append((kind, value))), \
             patch.object(room_helper_process, 'restore_paltalk', side_effect=lambda: events.append('restore')), \
             patch.object(room_helper_process, 'room_states', return_value=states), \
             patch.object(room_helper_process, 'navigate_my_rooms', side_effect=lambda: events.append('navigate')), \
             patch.object(room_helper_process, 'open_rooms', return_value=1) as opener:
            room_helper_process.main()
        return events, messages, opener

    def test_automatic_opens_only_closed_rooms(self):
        events, messages, opener = self.run_helper({'Alpha': True, 'Beta': False})
        self.assertEqual(events, ['restore', 'navigate'])
        self.assertEqual(opener.call_args.args[:2], (['Beta'], 7))
        self.assertIn(('result', 1), messages)
        self.assertIn(('message', 'Already open, skipping room: Alpha'), messages)

    def test_all_open_or_unknown_never_invokes_rooms(self):
        for state, result in [({'Alpha': True, 'Beta': True}, -3), (None, -2), ({'Alpha': False}, -2)]:
            with self.subTest(state=state):
                _, messages, opener = self.run_helper(state)
                opener.assert_not_called()
                self.assertIn(('result', result), messages)

    def test_automatic_worker_uses_isolated_helper_and_delay(self):
        worker = RoomWorker(['Alpha'], 8, automatic=True)
        results = []
        worker.completed.connect(results.append)
        with patch('paltalk_automation.room_opener.backend.room_workers.run_room_helper', return_value=1) as helper:
            worker.run()
        self.assertEqual(results, [1])
        self.assertEqual(helper.call_args.args[0:2], ('automatic', ['Alpha']))
        self.assertEqual(helper.call_args.kwargs['delay'], 8)

    def test_helper_failure_reports_unavailable(self):
        worker = RoomWorker(['Alpha'], 5, automatic=True)
        results = []
        worker.completed.connect(results.append)
        with patch('paltalk_automation.room_opener.backend.room_workers.run_room_helper', side_effect=RuntimeError('timed out')):
            worker.run()
        self.assertEqual(results, [RoomWorker.STATE_UNAVAILABLE])

    def test_manual_open_restores_and_opens(self):
        worker = RoomWorker(['Alpha'], 5)
        with patch('paltalk_automation.room_opener.backend.room_workers.restore_paltalk') as restore, \
             patch('paltalk_automation.room_opener.backend.room_workers.navigate_my_rooms') as navigate, \
             patch('paltalk_automation.room_opener.backend.room_workers.open_rooms', return_value=1) as opener:
            worker.run()
        restore.assert_called_once()
        navigate.assert_called_once()
        self.assertEqual(opener.call_args.args[0], ['Alpha'])

    def test_manual_navigation_failure_does_not_open_rooms(self):
        worker = RoomWorker(['Alpha'], 5)
        messages, results = [], []
        worker.message.connect(messages.append)
        worker.completed.connect(results.append)
        with patch('paltalk_automation.room_opener.backend.room_workers.restore_paltalk'), \
             patch('paltalk_automation.room_opener.backend.room_workers.navigate_my_rooms', side_effect=RuntimeError('My Rooms unavailable')), \
             patch('paltalk_automation.room_opener.backend.room_workers.open_rooms') as opener:
            worker.run()
        opener.assert_not_called()
        self.assertEqual(results, [-1])
        self.assertTrue(any('My Rooms unavailable' in message for message in messages))


if __name__ == '__main__':
    unittest.main()
