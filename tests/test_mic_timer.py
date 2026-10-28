import unittest
import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from PIL import Image, ImageDraw

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from paltalk_room_opener.mic_timer import MicTimeTracker, talking_now
from paltalk_room_opener.worker import MicTimerWorker
from paltalk_room_opener.main_window import MainWindow
from PySide6.QtWidgets import QApplication, QPlainTextEdit


def line(text):
    return {'text': text, 'words': [{'text': word} for word in text.split()]}


class TalkingNowTests(unittest.TestCase):
    def test_badge_and_its_ocr_text_are_excluded(self):
        image = Image.new('RGB', (200, 80), 'white')
        ImageDraw.Draw(image).rectangle((90, 25, 105, 40), fill=(0, 190, 50))
        row = {'text': 'xneilsterx 52 O', 'top': 26, 'bottom': 39, 'words': [
            {'text': 'xneilsterx', 'left': 20, 'right': 80},
            {'text': '52', 'left': 94, 'right': 104},
            {'text': 'O', 'left': 130, 'right': 139},
        ]}
        self.assertEqual(talking_now([line('Talking Now'), row, line('Mic Queue')], image), 'xneilsterx')

    def test_ambiguous_word_overlapping_badge_is_rejected(self):
        image = Image.new('RGB', (200, 80), 'white')
        ImageDraw.Draw(image).rectangle((90, 25, 105, 40), fill=(0, 190, 50))
        row = {'text': 'name 52', 'top': 26, 'bottom': 39, 'words': [
            {'text': 'name', 'left': 20, 'right': 80},
            {'text': '52', 'left': 88, 'right': 104},
        ]}
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            talking_now([line('Talking Now'), row, line('Mic Queue')], image)

    def test_reads_speaker_and_ignores_numeric_badge(self):
        self.assertEqual(talking_now([line('Talking Now'), line('peruvianito 34'), line('Mic Queue 2')]), 'peruvianito')

    def test_empty_section(self):
        self.assertEqual(talking_now([line('Talking Now'), line('Mic Queue 2')]), '')

    def test_missing_boundary_or_ambiguous_rows_are_unavailable(self):
        for lines in ([line('Talking Now'), line('person')],
                      [line('Talking Now'), line('one'), line('two'), line('Mic Queue')]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                talking_now(lines)


class MicTimeTrackerTests(unittest.TestCase):
    def test_progress_messages_are_at_least_15_seconds_apart(self):
        tracker = MicTimeTracker()
        tracker.observe((1,), 'oliver57', 0)
        first = tracker.observe((1,), 'oliver57', 5)
        self.assertTrue(any('on mic' in message for message in first))
        self.assertFalse(any('on mic' in message for message in tracker.observe((1,), 'oliver57', 10)))
        self.assertFalse(any('on mic' in message for message in tracker.observe((1,), 'oliver57', 19)))
        self.assertTrue(any('on mic' in message for message in tracker.observe((1,), 'oliver57', 20)))

    def test_room_switch_resumes_observed_time_without_counting_time_away(self):
        tracker = MicTimeTracker()
        tracker.observe((1,), 'oliver57', 0)
        tracker.observe((1,), 'oliver57', 5)
        tracker.observe((1,), 'oliver57', 10)
        tracker.observe((2,), 'andrew', 20)
        tracker.observe((2,), 'andrew', 25)
        tracker.observe((1,), 'oliver57', 100)
        messages = tracker.observe((1,), 'oliver57', 105)
        self.assertTrue(any('resumed oliver57' in message for message in messages))
        self.assertEqual(tracker.rooms[(1,)]['elapsed'], 15)

    def test_different_speaker_on_return_starts_fresh(self):
        tracker = MicTimeTracker()
        tracker.observe((1,), 'oliver57', 0)
        tracker.observe((1,), 'oliver57', 5)
        tracker.observe((2,), 'andrew', 10)
        tracker.observe((1,), 'someone else', 20)
        messages = tracker.observe((1,), 'someone else', 25)
        self.assertTrue(any('oliver57 finished' in message for message in messages))
        self.assertEqual(tracker.rooms[(1,)]['elapsed'], 5)

    def test_unreadable_interval_is_not_counted(self):
        tracker = MicTimeTracker()
        tracker.observe((1,), 'oliver57', 0)
        tracker.observe((1,), 'oliver57', 5)
        tracker.pause()
        tracker.observe((1,), 'oliver57', 100)
        tracker.observe((1,), 'oliver57', 105)
        self.assertEqual(tracker.rooms[(1,)]['elapsed'], 10)


class MicTimerRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = SimpleNamespace(mic_timer_rooms={},
                                      mic_timer_logs=[QPlainTextEdit() for _ in range(3)],
                                      mic_timer_status=MagicMock())
        self.worker = MicTimerWorker()
        self.worker.room_message.connect(lambda room, message: MainWindow.log_mic_timer_room(self.window, room, message))
        self.statuses = []
        self.worker.message.connect(self.statuses.append)

    def scan(self, room, speaker, now):
        self.worker.handle_scan({'room': [room], 'speaker': speaker}, now)

    def test_confirmed_speakers_are_routed_to_separate_room_logs(self):
        self.scan(1, 'oliver57', 0)
        self.assertIn('Waiting to confirm', self.statuses[-1])
        self.assertEqual(self.window.mic_timer_logs[0].toPlainText(), '')
        self.scan(1, 'oliver57', 5)
        self.assertIn('oliver57 started', self.window.mic_timer_logs[0].toPlainText())
        self.assertIn('Monitoring:', self.statuses[-1])
        self.scan(2, 'andrew', 10)
        self.scan(2, 'andrew', 15)
        self.assertIn('paused oliver57', self.window.mic_timer_logs[0].toPlainText())
        self.assertIn('andrew started', self.window.mic_timer_logs[1].toPlainText())
        self.scan(1, 'oliver57', 20)
        self.scan(1, 'oliver57', 25)
        self.assertIn('resumed oliver57', self.window.mic_timer_logs[0].toPlainText())

    def test_scan_error_and_empty_room_are_reported(self):
        with self.assertRaisesRegex(RuntimeError, 'OCR failed'):
            self.worker.handle_scan({'error': 'OCR failed'}, 0)
        self.worker.report_scan_error('OCR failed')
        self.assertIn('OCR failed', self.statuses[-1])
        self.scan(1, '', 1)
        self.scan(1, '', 2)
        self.assertIn('no one is on mic', self.statuses[-1])

    def test_fourth_room_shows_notice(self):
        for room in range(4):
            MainWindow.log_mic_timer_room(self.window, (room,), 'speaker')
        self.window.mic_timer_status.setText.assert_called_once()


if __name__ == '__main__':
    unittest.main()
