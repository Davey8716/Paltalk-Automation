import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from paltalk_room_opener import settings
from paltalk_room_opener.ui_tabs.advert_blocker_tab import AdvertBlockerTab


class AdvertIntegrationTests(unittest.TestCase):
    def test_toggle_starts_and_stops_tracker_and_persists_state(self):
        window = SimpleNamespace(advert_toggle=Mock(), advert_tracker=Mock(), log=Mock())
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(settings, 'APP_DATA_DIR', Path(directory)), \
             patch.object(settings, 'APP_STATE_PATH', Path(directory) / 'app_state.json'):
            settings.save_app_state(selected_tab='camera_opener')
            AdvertBlockerTab.set_advert_overlay_enabled(window, True)
            window.advert_tracker.start.assert_called_once()
            self.assertEqual(settings.load_app_state(), {
                'selected_tab': 'camera_opener', 'advert_overlay_enabled': True})
            AdvertBlockerTab.set_advert_overlay_enabled(window, False)
            window.advert_tracker.stop.assert_called_once()
            self.assertFalse(json.loads(settings.APP_STATE_PATH.read_text())['advert_overlay_enabled'])
            window.advert_toggle.setText.assert_called_with('Advert overlay: Off')

