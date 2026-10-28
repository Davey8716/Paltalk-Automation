import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paltalk_room_opener import settings


class RecentRoomsTests(unittest.TestCase):
    def test_history_merges_new_rooms_and_keeps_older_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', path), \
                 patch.object(settings, 'RECENT_ROOMS_PATH', path / 'recent_rooms.json'):
                self.assertEqual(settings.merge_recent_rooms(['Alpha', 'Beta', 'Alpha']), ['Alpha', 'Beta'])
                self.assertEqual(settings.merge_recent_rooms(['Gamma', 'Alpha']), ['Gamma', 'Alpha', 'Beta'])
                self.assertEqual(settings.merge_recent_rooms([]), ['Gamma', 'Alpha', 'Beta'])
                self.assertEqual(settings.load_recent_rooms(), ['Gamma', 'Alpha', 'Beta'])

    def test_invalid_saved_history_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recent_rooms.json'
            path.write_text(json.dumps({'invalid': True}), encoding='utf-8')
            with patch.object(settings, 'RECENT_ROOMS_PATH', path):
                with self.assertRaises(ValueError):
                    settings.merge_recent_rooms(['Alpha'])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'invalid': True})


if __name__ == '__main__':
    unittest.main()
