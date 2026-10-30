import os
import subprocess
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from paltalk_automation.room_opener.backend.room_workers import RoomStateWorker, RoomWorker, run_room_helper
from paltalk_automation.room_opener.backend import room_helper_process


class RoomHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def helper_process(stage, sleep=True):
        original_popen = subprocess.Popen
        code = ("import json,time; "
                f"print(json.dumps({{'kind':'stage','value':{stage!r}}}),flush=True); "
                + ("time.sleep(30)" if sleep else "pass"))
        def launch(*args, **kwargs):
            return original_popen([sys.executable, '-c', code], **kwargs)
        return patch('paltalk_automation.room_opener.backend.room_workers.subprocess.Popen', side_effect=launch)

    def test_invocation_timeout_reports_unknown_outcome(self):
        with self.helper_process('invoking room tile'), \
             self.assertRaisesRegex(RuntimeError, 'invoking room tile.*outcome is unknown'):
            run_room_helper('single', ['Alpha'], lambda: False, timeout=0.5)

    def test_state_scan_timeout_reports_its_stage(self):
        with self.helper_process('room-state scan'), \
             self.assertRaisesRegex(RuntimeError, 'timed out during room-state scan'):
            run_room_helper('states', ['Alpha'], lambda: False, timeout=0.5)

    def test_helper_exit_without_result_is_reported(self):
        with self.helper_process('finding room tile', sleep=False), \
             self.assertRaisesRegex(RuntimeError, 'exited during finding room tile'):
            run_room_helper('single', ['Alpha'], lambda: False, timeout=2)

    def test_stalled_single_room_keeps_qt_event_loop_responsive(self):
        worker = RoomWorker(['Alpha'], 5, check_existing=True)
        loop = QEventLoop()
        ticks, messages = [], []
        timer = QTimer()
        timer.setInterval(30)
        timer.timeout.connect(lambda: ticks.append(1))
        worker.message.connect(messages.append)
        worker.finished.connect(loop.quit)
        def bounded(action, names, interrupted, message):
            return run_room_helper(action, names, interrupted, message, timeout=0.5)
        with self.helper_process('invoking room tile'), \
             patch('paltalk_automation.room_opener.backend.room_workers.run_room_helper', side_effect=bounded):
            timer.start()
            worker.start()
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            timer.stop()
            self.assertTrue(worker.wait(2000))
        self.assertGreater(len(ticks), 2)
        self.assertTrue(any('outcome is unknown' in message for message in messages))

    def test_interrupted_scan_emits_no_stale_result(self):
        worker = RoomStateWorker(['Alpha'])
        results = []
        worker.result.connect(results.append)
        with patch('paltalk_automation.room_opener.backend.room_workers.run_room_helper', side_effect=RuntimeError('stopped')), \
             patch.object(worker, 'isInterruptionRequested', return_value=True):
            worker.run()
        self.assertEqual(results, [])

    def test_single_action_restores_and_toggles_fresh_state(self):
        for state in (True, False, None, {}):
            events = []
            states = {'Alpha': state} if isinstance(state, bool) else state
            with self.subTest(state=state), \
                 patch('sys.argv', ['helper', 'single', '["Alpha"]', '5']), \
                 patch.object(room_helper_process, 'send', side_effect=lambda kind, value: events.append((kind, value))), \
                 patch.object(room_helper_process, 'restore_paltalk') as restore, \
                 patch.object(room_helper_process, 'room_states', return_value=states), \
                 patch.object(room_helper_process, 'close_room') as close, \
                 patch.object(room_helper_process, 'navigate_my_rooms') as navigate, \
                 patch.object(room_helper_process, 'open_rooms', return_value=1) as opener:
                room_helper_process.main()
            restore.assert_called_once()
            self.assertEqual(close.call_count, int(state is True))
            self.assertEqual(opener.call_count, int(state is False))
            self.assertEqual(navigate.call_count, int(state is False))
            if state is None or state == {}:
                self.assertIn(('result', -2), events)

    def test_single_restore_failure_does_not_change_room(self):
        events = []
        with patch('sys.argv', ['helper', 'single', '["Alpha"]']), \
             patch.object(room_helper_process, 'send', side_effect=lambda kind, value: events.append((kind, value))), \
             patch.object(room_helper_process, 'restore_paltalk', side_effect=RuntimeError('unavailable')), \
             patch.object(room_helper_process, 'room_states') as states, \
             patch.object(room_helper_process, 'close_room') as close, \
             patch.object(room_helper_process, 'open_rooms') as opener:
            room_helper_process.main()
        states.assert_not_called()
        close.assert_not_called()
        opener.assert_not_called()
        self.assertTrue(any(kind == 'error' and 'unavailable' in value for kind, value in events))

    def test_navigation_failure_stops_single_and_automatic_opening(self):
        for action in ('single', 'automatic'):
            events = []
            with self.subTest(action=action), \
                 patch('sys.argv', ['helper', action, '["Alpha"]']), \
                 patch.object(room_helper_process, 'send', side_effect=lambda kind, value: events.append((kind, value))), \
                 patch.object(room_helper_process, 'restore_paltalk'), \
                 patch.object(room_helper_process, 'room_states', return_value={'Alpha': False}), \
                 patch.object(room_helper_process, 'navigate_my_rooms', side_effect=RuntimeError('tab unavailable')), \
                 patch.object(room_helper_process, 'open_rooms') as opener:
                room_helper_process.main()
            opener.assert_not_called()
            self.assertTrue(any(kind == 'error' and 'tab unavailable' in value for kind, value in events))


if __name__ == '__main__':
    unittest.main()
