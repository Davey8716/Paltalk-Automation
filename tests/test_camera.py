import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from paltalk_room_opener import settings
from paltalk_room_opener.camera_automation import CameraScanner, _camera_state, _normal


class CameraTests(unittest.TestCase):
    def test_camera_settings_are_separate_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', root), patch.object(settings, 'CAMERA_SETTINGS_PATH', root / 'cameras.json'):
                settings.save_camera_settings(['Dave8787', 'margot73'], True)
                self.assertEqual(settings.load_camera_settings(), {'usernames': ['Dave8787', 'margot73'], 'start_on_paltalk': True})
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
        self.assertEqual(e.pattern.calls, 1)


if __name__ == '__main__':
    unittest.main()
