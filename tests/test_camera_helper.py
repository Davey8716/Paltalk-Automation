import os
import subprocess
import sys
import unittest
from unittest.mock import patch

import psutil
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from paltalk_automation.camera_opener.backend.camera_worker import CameraWorker


class CameraHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def launch_script(code):
        real_popen = subprocess.Popen
        return patch('paltalk_automation.camera_opener.backend.camera_worker.subprocess.Popen',
                     side_effect=lambda *args, **kwargs: real_popen([sys.executable, '-c', code], **kwargs))

    def test_timeout_while_opening_reports_unknown_outcome(self):
        code = ("import json,time; print(json.dumps({'kind':'progress','value':'opening a camera'}), flush=True); "
                "time.sleep(30)")
        worker = CameraWorker(['Alice'])
        with self.launch_script(code), self.assertRaisesRegex(RuntimeError, 'outcome is unknown'):
            worker.run_helper(timeout=0.5)

    def test_timeout_restarts_and_ui_remains_responsive(self):
        worker = CameraWorker(['Alice'])
        loop = QEventLoop()
        ticks, messages, calls = [], [], []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.append(1))
        worker.message.connect(messages.append)
        worker.finished.connect(loop.quit)

        def run_helper():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('scan timed out')
            worker.requestInterruption()

        with patch.object(worker, 'run_helper', side_effect=run_helper):
            timer.start()
            worker.start()
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            timer.stop()
            self.assertTrue(worker.wait(2000))
        self.assertEqual(len(calls), 2)
        self.assertGreater(len(ticks), 2)
        self.assertTrue(any('timed out' in message for message in messages))

    def test_progress_and_messages_are_forwarded(self):
        code = ("import json,time; "
                "[print(json.dumps({'kind':k,'value':v}),flush=True) for k,v in "
                "[('progress','scanning'),('message','activity'),('invoked','opened'),('failed','missed')]]; "
                "time.sleep(30)")
        worker = CameraWorker(['Alice'])
        values = []
        worker.message.connect(lambda value: values.append(('message', value)))
        worker.invoked.connect(lambda value: values.append(('invoked', value)))
        worker.failed.connect(lambda value: values.append(('failed', value)))
        with self.launch_script(code), self.assertRaisesRegex(RuntimeError, 'Timed out'):
            worker.run_helper(timeout=0.5)
        self.assertEqual(values, [('message', 'activity'), ('invoked', 'opened'), ('failed', 'missed')])

    def test_live_status_is_forwarded(self):
        code = ("import json,time; print(json.dumps({'kind':'live_status','value':['Alice']}),flush=True); "
                "time.sleep(30)")
        worker = CameraWorker(['Alice'])
        values = []
        worker.live_status.connect(values.append)
        with self.launch_script(code), self.assertRaisesRegex(RuntimeError, 'Timed out'):
            worker.run_helper(timeout=0.5)
        self.assertEqual(values, [['Alice']])

    def test_stop_terminates_helper_and_ocr_child(self):
        code = ("import json,subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "print(json.dumps({'kind':'message','value':str(p.pid)}),flush=True); time.sleep(30)")
        worker = CameraWorker(['Alice'])
        loop = QEventLoop()
        children = []
        def received(value):
            children.append(int(value))
            worker.requestInterruption()
        worker.message.connect(received)
        worker.finished.connect(loop.quit)
        with self.launch_script(code):
            worker.start()
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            if worker.isRunning():
                worker.requestInterruption()
            self.assertTrue(worker.wait(3000))
        self.assertEqual(len(children), 1)
        self.assertFalse(psutil.pid_exists(children[0]))

    def test_name_updates_reach_running_helper(self):
        code = ("import json,sys,time; "
                "print(json.dumps({'kind':'message','value':'ready'}),flush=True); "
                "line=sys.stdin.readline(); "
                "print(json.dumps({'kind':'message','value':line.strip()}),flush=True); time.sleep(30)")
        worker = CameraWorker(['Alice'])
        loop = QEventLoop()
        messages = []
        def received(value):
            messages.append(value)
            if value == 'ready':
                worker.update_names(['Alice', 'Bob'])
            else:
                worker.requestInterruption()
        worker.message.connect(received)
        worker.finished.connect(loop.quit)
        with self.launch_script(code):
            worker.start()
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            if worker.isRunning():
                worker.requestInterruption()
            self.assertTrue(worker.wait(3000))
        self.assertEqual(messages, ['ready', '["Alice", "Bob"]'])

    def test_portrait_toggle_reaches_running_helper(self):
        code = ("import json,sys,time; "
                "print(json.dumps({'kind':'message','value':'ready'}),flush=True); "
                "line=sys.stdin.readline(); "
                "print(json.dumps({'kind':'message','value':line.strip()}),flush=True); time.sleep(30)")
        worker = CameraWorker(['Alice'])
        loop = QEventLoop()
        messages = []
        def received(value):
            messages.append(value)
            if value == 'ready':
                worker.update_portrait_adjustment(False)
            else:
                worker.requestInterruption()
        worker.message.connect(received)
        worker.finished.connect(loop.quit)
        with self.launch_script(code):
            worker.start()
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            if worker.isRunning():
                worker.requestInterruption()
            self.assertTrue(worker.wait(3000))
        self.assertEqual(messages, ['ready', '{"portrait_adjustment": false}'])


if __name__ == '__main__':
    unittest.main()
