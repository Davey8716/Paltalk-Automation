import unittest
from unittest.mock import MagicMock, patch

import main
from paltalk_automation import helper_process as worker


class HelperLaunchTests(unittest.TestCase):
    def test_commands_for_source_and_frozen_app(self):
        with patch.object(worker.sys, 'executable', 'app.exe'), patch.object(worker.sys, 'frozen', False, create=True):
            self.assertEqual(worker.helper_command('room_helper_process', 'single'),
                             ['app.exe', '-m', 'paltalk_automation.room_opener.backend.room_helper_process', 'single'])
        with patch.object(worker.sys, 'executable', 'app.exe'), patch.object(worker.sys, 'frozen', True, create=True):
            self.assertEqual(worker.helper_command('room_helper_process', 'single'),
                             ['app.exe', '--helper', 'room_helper_process', 'single'])

    def test_helper_dispatch_bypasses_mutex_and_forwards_arguments(self):
        from paltalk_automation.room_opener.backend import room_helper_process
        with patch.object(main.sys, 'argv', ['app.exe', '--helper', 'room_helper_process', 'single']), \
             patch.object(main, 'SingleInstance') as instance, \
             patch.object(room_helper_process, 'main') as helper:
            self.assertEqual(main.main(), 0)
            self.assertEqual(main.sys.argv, ['app.exe', 'single'])
            helper.assert_called_once_with()
            instance.assert_not_called()

    def test_duplicate_instance_exits_without_creating_window(self):
        instance = MagicMock(already_running=True)
        with patch.object(main, 'SingleInstance', return_value=instance), \
             patch.object(main, 'QApplication'), patch.object(main, 'MainWindow') as window:
            self.assertEqual(main.main(), 0)
            window.assert_not_called()
            instance.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
