import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

with patch('importlib.util.find_spec', return_value=object()):
    import main
from paltalk_room_opener import settings


class StartInTrayTests(unittest.TestCase):
    def test_settings_preserve_tab_and_tray_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', path), \
                 patch.object(settings, 'APP_STATE_PATH', path / 'app_state.json'):
                settings.save_app_state('camera_opener')
                settings.save_app_state(start_in_tray=True)
                settings.save_app_state('room_opener')
                self.assertEqual(settings.load_app_state(), {
                    'selected_tab': 'room_opener', 'start_in_tray': True,
                })
                settings.save_app_state(start_in_tray=False)
                self.assertFalse(settings.load_app_state()['start_in_tray'])

    def test_startup_visibility_and_tray_fallback(self):
        for enabled, tray_available, visible in ((True, True, False), (False, True, True), (True, False, True)):
            with self.subTest(enabled=enabled, tray_available=tray_available):
                window = MagicMock()
                window.start_in_tray.isChecked.return_value = enabled
                window.tray_icon = object() if tray_available else None
                instance = MagicMock(already_running=False)
                app = MagicMock()
                with patch.object(main, 'SingleInstance', return_value=instance), \
                     patch.object(main, 'QApplication', return_value=app), \
                     patch.object(main, 'MainWindow', return_value=window):
                    main.main()
                self.assertEqual(window.show.call_count, int(visible))
                app.exec.assert_called_once()


if __name__ == '__main__':
    unittest.main()
