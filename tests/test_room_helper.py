import os
import subprocess
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from paltalk_room_opener.worker import RoomStateWorker, RoomWorker, run_room_helper


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
        return patch('paltalk_room_opener.worker.subprocess.Popen', side_effect=launch)

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
             patch('paltalk_room_opener.worker.run_room_helper', side_effect=bounded):
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
        with patch('paltalk_room_opener.worker.run_room_helper', side_effect=RuntimeError('stopped')), \
             patch.object(worker, 'isInterruptionRequested', return_value=True):
            worker.run()
        self.assertEqual(results, [])


if __name__ == '__main__':
    unittest.main()
