import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

with patch('importlib.util.find_spec', return_value=object()):
    import main
from paltalk_automation import settings
from paltalk_automation.main_window import MainWindow
from PySide6.QtWidgets import QSystemTrayIcon
from paltalk_automation.foreground import ForegroundTracker


class StartInTrayTests(unittest.TestCase):
    def test_startup_status_updates_all_tab_labels(self):
        window = MagicMock()
        window.windows_startup_status_labels = [MagicMock() for _ in range(5)]
        window.start_with_windows.isEnabled.return_value = True
        for enabled in (True, False):
            window.start_with_windows.isChecked.return_value = enabled
            MainWindow.update_windows_startup_status(window)
            for label in window.windows_startup_status_labels:
                label.setText.assert_called_with(f'Start with Windows: {"On" if enabled else "Off"}')
        window.start_with_windows.isEnabled.return_value = False
        MainWindow.update_windows_startup_status(window)
        for label in window.windows_startup_status_labels:
            label.setText.assert_called_with('Start with Windows: Unavailable')

    def test_tray_click_toggles_active_window_and_restores_inactive_window(self):
        for visible, minimized, active, hides in (
            (True, False, True, True),
            (True, False, False, False),
            (True, True, False, False),
            (False, False, False, False),
        ):
            with self.subTest(visible=visible, minimized=minimized, active=active):
                window = MagicMock()
                window.isVisible.return_value = visible
                window.isMinimized.return_value = minimized
                window.foreground_tracker.is_foreground.return_value = active
                MainWindow.tray_activated(window, QSystemTrayIcon.ActivationReason.Trigger)
                self.assertEqual(window.hide.call_count, int(hides))
                self.assertEqual(window.restore_from_tray.call_count, int(not hides))

    def test_double_click_notification_does_not_toggle_twice(self):
        window = MagicMock()
        MainWindow.tray_activated(window, QSystemTrayIcon.ActivationReason.DoubleClick)
        window.hide.assert_not_called()
        window.restore_from_tray.assert_not_called()

    def test_foreground_tracking_ignores_taskbar_but_records_other_apps(self):
        tracker = ForegroundTracker.__new__(ForegroundTracker)
        tracker.last_window = 0
        tracker._user32 = MagicMock()
        tracker._user32.GetAncestor.side_effect = lambda hwnd, flag: hwnd
        classes = {10: 'QtWindow', 20: 'Shell_TrayWnd', 30: 'OtherApp',
                   40: 'NotifyIconOverflowWindow'}
        def get_class(hwnd, buffer, size):
            buffer.value = classes[hwnd]
        tracker._user32.GetClassNameW.side_effect = get_class
        tracker._remember(10)
        tracker._remember(20)
        self.assertEqual(tracker.last_window, 10)
        tracker._remember(30)
        tracker._remember(40)
        self.assertEqual(tracker.last_window, 30)

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
