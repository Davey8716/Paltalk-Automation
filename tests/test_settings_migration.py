import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paltalk_room_opener import settings


class SettingsMigrationTests(unittest.TestCase):
    def test_copies_missing_files_once_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = root / 'roaming', root / 'local'
            old.mkdir()
            new.mkdir()
            (old / 'camera_names.json').write_text('old cameras', encoding='utf-8')
            (old / 'room_names.json').write_text('old rooms', encoding='utf-8')
            (new / 'room_names.json').write_text('local rooms', encoding='utf-8')
            with patch.object(settings, 'APP_DATA_DIR', new), patch.object(settings, 'LEGACY_DATA_DIR', old):
                settings.migrate_legacy_settings()
                self.assertEqual((new / 'camera_names.json').read_text(), 'old cameras')
                self.assertEqual((new / 'room_names.json').read_text(), 'local rooms')
                (new / 'camera_names.json').unlink()
                settings.migrate_legacy_settings()
                self.assertFalse((new / 'camera_names.json').exists())
                self.assertTrue((old / 'camera_names.json').exists())

    def test_failure_does_not_mark_migration_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = root / 'roaming', root / 'local'
            old.mkdir()
            (old / 'camera_names.json').write_text('saved', encoding='utf-8')
            with patch.object(settings, 'APP_DATA_DIR', new), patch.object(settings, 'LEGACY_DATA_DIR', old), \
                 patch.object(Path, 'read_bytes', side_effect=OSError('read failed')):
                with self.assertRaises(OSError):
                    settings.migrate_legacy_settings()
            self.assertFalse((new / '.roaming-migration-complete').exists())

    def test_recent_history_is_copied_to_new_name_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / 'recent_rooms.json'
            new = root / 'recently visited.json'
            old.write_text('["Alpha"]', encoding='utf-8')
            with patch.object(settings, 'APP_DATA_DIR', root), patch.object(settings, 'RECENT_ROOMS_PATH', new):
                settings.migrate_recent_history()
                self.assertEqual(new.read_text(encoding='utf-8'), '["Alpha"]')
                self.assertTrue(old.exists())
                new.write_text('["Beta"]', encoding='utf-8')
                settings.migrate_recent_history()
                self.assertEqual(new.read_text(encoding='utf-8'), '["Beta"]')


if __name__ == '__main__':
    unittest.main()
