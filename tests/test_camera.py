import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from paltalk_room_opener import settings
from paltalk_room_opener.camera_automation import (
    CameraScanner, _badge_boxes, _button_section, _camera_error_message, _camera_state, _match_rows, _normal,
    _ocr, _row_text, _row_words, _section_words, _sections, _ScanStopped, watch_cameras,
)


class CameraTests(unittest.TestCase):
    def test_automation_errors_are_reported_without_dotnet_stack_trace(self):
        error = RuntimeError('Unrecognized error.\n   at MS.Internal.Automation.UiaCoreApi.CheckError(Int32 hr)')
        self.assertEqual(_camera_error_message(error), 'Paltalk controls are temporarily unavailable. Retrying.')
        self.assertEqual(_camera_error_message(RuntimeError('Windows OCR timed out.')), 'Windows OCR timed out.')

    def test_room_mode_save_preserves_other_saved_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', root), patch.object(settings, 'SETTINGS_PATH', root / 'rooms.json'):
                settings.save_settings(['Room'], 3, 'regular', False)
                settings.save_room_mode('vip')
                data = settings.load_settings()
                self.assertEqual(data['mode'], 'vip')
                self.assertEqual(data['rooms']['room_1'], 'Room')

    def test_camera_settings_are_separate_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', root), patch.object(settings, 'CAMERA_SETTINGS_PATH', root / 'cameras.json'):
                settings.save_camera_settings(['Dave8787', 'margot73'], True, True)
                self.assertEqual(settings.load_camera_settings(), {'usernames': ['Dave8787', 'margot73'], 'start_on_paltalk': True, 'alphabetical': True})
                self.assertFalse((root / 'room_names.json').exists())

    def test_icon_states_and_ocr_whitespace(self):
        for color, expected in [((30, 150, 240), 'available'), ((40, 210, 30), 'open'), ((220, 220, 220), 'unknown')]:
            self.assertEqual(_camera_state(Image.new('RGB', (16, 16), color), 0, 0, 16, 16), expected)
        self.assertEqual(_normal('Candy licker 1969'), _normal('candylicker1969'))

    def test_recheck_uses_fresh_row_and_skips_ambiguous_or_open(self):
        class Pattern:
            def __init__(self): self.calls = 0
            def Invoke(self): self.calls += 1
        class Element:
            def __init__(self): self.pattern = Pattern()
            def GetCurrentPattern(self, _): return self.pattern
        e = Element()
        scanner = CameraScanner.__new__(CameraScanner)
        scanner.a = type('A', (), {'InvokePattern': type('P', (), {'Pattern': 1})})
        scanner.scan = lambda: [('Tiffee', 'available', e, 10)]
        self.assertTrue(scanner.open_if_available('tiffee'))
        scanner.scan = lambda: [('Tiffee', 'open', e, 10)]
        self.assertFalse(scanner.open_if_available('tiffee'))
        scanner.scan = lambda: [('Tiffee', 'available', e, 10), ('Tiffee', 'available', e, 30)]
        self.assertFalse(scanner.open_if_available('tiffee'))
        scanner.room_identity = (1,)
        def changed_room():
            scanner.room_identity = (2,)
            return [('Tiffee', 'available', e, 30)]
        scanner.scan = changed_room
        self.assertFalse(scanner.open_if_available('tiffee'))
        self.assertEqual(e.pattern.calls, 1)

    def test_badge_shapes_and_row_word_boundaries(self):
        image = Image.new('RGB', (200, 24), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 5, 92, 18), fill=(0, 155, 220))
        boxes = _badge_boxes(image, 0, 0, 180, 24)
        self.assertEqual(boxes, [(80, 5, 93, 19)])
        lines = [{'words': [
            {'text': 'FATPIZZA', 'left': 5, 'right': 75, 'top': 6, 'bottom': 18},
            {'text': 'O', 'left': 82, 'right': 91, 'top': 6, 'bottom': 18},
            {'text': 'other', 'left': 5, 'right': 50, 'top': 35, 'bottom': 47},
        ]}]
        words = _row_words(lines, 12, 180)
        self.assertEqual(_row_text(words, boxes[0][0]), 'FATPIZZA')
        self.assertIsNone(_row_text(words, 70))

    def test_grey_admin_badge_is_excluded_from_username(self):
        image = Image.new('RGB', (160, 24), 'white')
        draw = ImageDraw.Draw(image)
        draw.ellipse((82, 5, 95, 18), fill=(128, 128, 128))
        draw.text((85, 6), 'A', fill='white')
        boxes = _badge_boxes(image, 0, 0, 150, 24)
        self.assertEqual(len(boxes), 1)
        words = [{'text': 'andrew777a', 'left': 5, 'right': 78},
                 {'text': 'O', 'left': 83, 'right': 94}]
        self.assertEqual(_row_text(words, boxes[0][0]), 'andrew777a')

    def test_outlined_badge_and_colored_badges_are_detected(self):
        image = Image.new('RGB', (200, 24), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 4, 94, 19), outline=(150, 150, 150), width=2)
        draw.rectangle((110, 5, 124, 18), fill=(255, 165, 0))
        draw.polygon([(140, 5), (154, 5), (154, 14), (147, 19), (140, 14)], fill=(0, 150, 220))
        boxes = _badge_boxes(image, 0, 0, 190, 24)
        self.assertEqual([box[0] for box in boxes], [80, 110, 140])
        words = [{'text': 'andrew_vanart', 'left': 2, 'right': 76},
                 {'text': 'O', 'left': 82, 'right': 92}]
        self.assertEqual(_row_text(words, boxes[0][0]), 'andrew_vanart')

    def test_exact_readings_match_saved_names(self):
        rows = [
            (('TungfooMaster1',), 'available', object(), 10),
            (('thailand', 'sexydiva thailand', "se)9'diva thailand"), 'available', object(), 30),
            (('Thai_mafia 1', 'Thai_mafial'), 'available', object(), 50),
            (('FATPIZZA',), 'available', object(), 70),
            (('SHARKCAT',), 'available', object(), 90),
        ]
        names = ['TungfooMaster1', 'sexydiva thailand', 'Thai_mafia1', 'FATPIZZA', 'SHARKCAT']
        for name in names:
            matches, conflict = _match_rows(rows, names, name)
            self.assertEqual(len(matches), 1, name)
            self.assertFalse(conflict, name)
        self.assertEqual(_match_rows(rows, ['sexydiva'], 'sexydiva')[0], [])

    def test_conflicting_and_duplicate_rows_are_not_unique(self):
        rows = [(('Thai_mafia1', 'Thai_mafial'), 'available', object(), 10)]
        names = ['Thai_mafia1', 'Thai_mafial']
        self.assertTrue(_match_rows(rows, names, 'Thai_mafia1')[1])
        rows.append((('Thai_mafia 1',), 'available', object(), 30))
        self.assertEqual(len(_match_rows(rows, names, 'Thai_mafia1')[0]), 2)

    def test_recheck_skips_conflicting_saved_names(self):
        scanner = CameraScanner.__new__(CameraScanner)
        scanner.scan = lambda: [(('Thai_mafia1', 'Thai_mafial'), 'available', object(), 10)]
        self.assertFalse(scanner.open_if_available('Thai_mafia1', configured_names=['Thai_mafia1', 'Thai_mafial']))

    def test_recheck_invokes_new_row_after_reordering(self):
        class Pattern:
            calls = 0
            def Invoke(self): self.calls += 1
        class Element:
            def __init__(self): self.pattern = Pattern()
            def GetCurrentPattern(self, _): return self.pattern
        old, moved = Element(), Element()
        scanner = CameraScanner.__new__(CameraScanner)
        scanner.a = type('A', (), {'InvokePattern': type('P', (), {'Pattern': 1})})
        scanner.scan = lambda: [(('TungfooMaster1',), 'available', moved, 50)]
        self.assertTrue(scanner.open_if_available('TungfooMaster1'))
        self.assertEqual(old.pattern.calls, 0)
        self.assertEqual(moved.pattern.calls, 1)

    def test_scaled_word_positions_and_space_preservation(self):
        lines = [{'words': [
            {'text': 'sexydiva', 'left': 10, 'right': 90, 'top': 12, 'bottom': 36},
            {'text': 'thailand', 'left': 96, 'right': 166, 'top': 12, 'bottom': 36},
            {'text': 'camera', 'left': 200, 'right': 230, 'top': 12, 'bottom': 36},
        ]}]
        self.assertEqual(_row_text(_row_words(lines, 12, 100, 2)), 'sexydiva thailand')

    def test_visible_section_boundaries(self):
        lines = [{'text': 'Mic Queue 6', 'top': 0, 'bottom': 15},
                 {'text': 'Join Queue to Talk', 'top': 20, 'bottom': 35},
                 {'text': 'On Cam 10', 'top': 200, 'bottom': 215},
                 {'text': 'Chatting', 'top': 500, 'bottom': 515}]
        self.assertEqual(_sections(lines, 800), [('Mic Queue', 15, 200), ('On Cam', 215, 500)])
        self.assertEqual(_sections(lines[2:], 800), [('On Cam', 215, 500)])
        self.assertEqual(_sections(lines[:2], 800), [('Mic Queue', 15, 800)])
        with self.assertRaises(RuntimeError):
            _sections([lines[1]], 800)
        with self.assertRaises(RuntimeError):
            _sections([lines[0], lines[0]], 800)

    def test_queue_position_is_separate_from_username(self):
        def word(text, left, right):
            return {'text': text, 'left': left, 'right': right}
        for name in ('lauriec40', 'ReMarkable1960', '1SweeTart'):
            words = [word('4', 2, 8), word(name, 18, 90)]
            self.assertEqual(_row_text(_section_words(words, 'Mic Queue')), name)
            self.assertEqual(_row_text(_section_words(words, 'On Cam')), '4 ' + name)
        words = [word('1SweeTart', 18, 90)]
        self.assertEqual(_row_text(_section_words(words, 'Mic Queue')), '1SweeTart')
        words = [word('4', 2, 20), word('1SweeTart', 18, 90)]
        self.assertEqual(_row_text(_section_words(words, 'Mic Queue')), '4 1SweeTart')
        words = [word('123', 25, 50), word('O', 55, 65)]
        self.assertEqual(_row_text(_section_words(words, 'Mic Queue')), '123 O')

    def test_join_queue_button_is_not_a_camera_row(self):
        sections = [('Mic Queue', 15, 200), ('On Cam', 215, 500)]
        join = SimpleNamespace(ControlType='button', IsOffscreen=False, AutomationId='JoinQueueButton')
        camera = SimpleNamespace(ControlType='button', IsOffscreen=False, AutomationId='MemberContentWidget:camera')
        self.assertIsNone(_button_section(join, 'button', 20, 20, sections))
        self.assertEqual(_button_section(camera, 'button', 70, 16, sections), 'Mic Queue')
        self.assertIsNone(_button_section(camera, 'button', 195, 16, sections))

    def test_stop_during_delay_prevents_next_camera(self):
        class Scanner:
            room_identity = (1,)
            ocr_lines = []
            ocr_comparisons = []
            calls = []
            def scan(self):
                return [(('first',), 'available', object(), 10),
                        (('second',), 'available', object(), 30)]
            def open_if_available(self, name, stopped, names):
                self.calls.append(name)
                return True
        scanner = Scanner()
        ticks = []
        with patch('paltalk_room_opener.camera_automation.CameraScanner', return_value=scanner), \
             patch('paltalk_room_opener.camera_automation.time.sleep', side_effect=lambda _: ticks.append(1)):
            watch_cameras(['first', 'second'], lambda _: None, lambda: len(ticks) >= 3)
        self.assertEqual(scanner.calls, ['first'])
        self.assertEqual(len(ticks), 3)

    def test_stopping_ocr_terminates_the_process(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch('paltalk_room_opener.camera_automation.subprocess.Popen', return_value=process):
            with self.assertRaises(_ScanStopped):
                _ocr(Image.new('RGB', (10, 10), 'white'), lambda: True)
        process.kill.assert_called_once()
        process.communicate.assert_called_once()

    def test_new_names_are_used_on_next_scan(self):
        class Scanner:
            room_identity = (1,)
            ocr_lines = []
            ocr_comparisons = []
            def __init__(self):
                self.scans = 0
                self.opened = []
            def scan(self):
                self.scans += 1
                return [(('Bob',), 'available', object(), 10, 'On Cam')]
            def open_if_available(self, name, stopped, names):
                self.opened.append(name)
                return True
        scanner = Scanner()
        names = ['Alice']
        ticks = []
        def sleep(_):
            ticks.append(1)
            if len(ticks) == 1:
                names.append('Bob')
        with patch('paltalk_room_opener.camera_automation.CameraScanner', return_value=scanner), \
             patch('paltalk_room_opener.camera_automation.time.sleep', side_effect=sleep):
            watch_cameras(names, lambda _: None, lambda: len(ticks) >= 22,
                          current_names=lambda: list(names))
        self.assertEqual(scanner.opened, ['Bob'])

    def test_live_status_tracks_only_confirmed_visible_cameras(self):
        class Scanner:
            room_identity = (1,)
            ocr_lines = []
            ocr_comparisons = []
            def scan(self):
                return [(('Alice',), 'open', object(), 10, 'On Cam'),
                        (('Bob',), 'unknown', object(), 30, 'On Cam')]
        snapshots = []
        with patch('paltalk_room_opener.camera_automation.CameraScanner', return_value=Scanner()):
            watch_cameras(['Alice', 'Bob', 'Carol'], lambda _: None, lambda: bool(snapshots),
                          live_status=lambda names: snapshots.append(names))
        self.assertEqual(snapshots, [['Alice']])

    def test_opening_confirmed_only_after_fresh_green_icon(self):
        class Scanner:
            room_identity = (1,)
            ocr_lines = []
            ocr_comparisons = []
            scans = 0
            opens = 0
            def scan(self):
                self.scans += 1
                return [(('Alice',), 'available' if self.scans == 1 else 'open', object(), 10, 'On Cam')]
            def open_if_available(self, *args):
                self.opens += 1
                return True
        scanner = Scanner()
        confirmed, failed, clock = [], [], [10.0]
        with patch('paltalk_room_opener.camera_automation.CameraScanner', return_value=scanner), \
             patch('paltalk_room_opener.camera_automation.time.monotonic', side_effect=lambda: clock[0]), \
             patch('paltalk_room_opener.camera_automation.time.sleep', side_effect=lambda t: clock.__setitem__(0, clock[0] + t)):
            watch_cameras(['Alice'], lambda _: None, lambda: any('confirmed' in message for message in confirmed),
                          invoked=confirmed.append, failed=failed.append)
        self.assertEqual(scanner.opens, 1)
        self.assertGreaterEqual(scanner.scans, 2)
        self.assertIn('waiting for confirmation', confirmed[0])
        self.assertIn('confirmed', confirmed[1])
        self.assertEqual(failed, [])

    def test_unconfirmed_attempt_is_not_reinvoked_while_waiting(self):
        class Scanner:
            room_identity = (1,)
            ocr_lines = []
            ocr_comparisons = []
            opens = 0
            def scan(self):
                return [(('Alice',), 'available', object(), 10, 'On Cam')]
            def open_if_available(self, *args):
                self.opens += 1
                return True
        scanner = Scanner()
        confirmed, failed, clock = [], [], [10.0]
        with patch('paltalk_room_opener.camera_automation.CameraScanner', return_value=scanner), \
             patch('paltalk_room_opener.camera_automation.time.monotonic', side_effect=lambda: clock[0]), \
             patch('paltalk_room_opener.camera_automation.time.sleep', side_effect=lambda t: clock.__setitem__(0, clock[0] + t)):
            watch_cameras(['Alice'], lambda _: None, lambda: bool(failed),
                          invoked=confirmed.append, failed=failed.append)
        self.assertEqual(scanner.opens, 1)
        self.assertEqual(len(confirmed), 1)
        self.assertIn('waiting for confirmation', confirmed[0])
        self.assertIn('could not be confirmed', failed[0])


if __name__ == '__main__':
    unittest.main()
