import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QLineEdit
from paltalk_automation.main_window import MainWindow


class DuplicateRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_duplicate_edit_is_cleared_and_not_saved(self):
        fields = [QLineEdit('The Garage'), QLineEdit('  the garage  ')]
        window = SimpleNamespace(rooms=fields, log=MagicMock(), save_current_settings=MagicMock(),
                                 set_room_duplicate=MainWindow.set_room_duplicate)
        MainWindow.finish_room_edit(window, fields[1])
        self.assertEqual(fields[0].text(), 'The Garage')
        self.assertEqual(fields[1].text(), '')
        window.save_current_settings.assert_called_once_with(announce=False)
        window.log.appendPlainText.assert_called_once()

    def test_only_the_edited_duplicate_gets_red_state_and_correction_clears_it(self):
        fields = [QLineEdit('Alpha'), QLineEdit(' alpha ')]
        window = SimpleNamespace(rooms=fields, save_current_settings=MagicMock(),
                                 set_room_duplicate=MainWindow.set_room_duplicate)
        MainWindow.room_text_edited(window, fields[1])
        self.assertTrue(fields[1].property('roomDuplicate'))
        self.assertFalse(bool(fields[0].property('roomDuplicate')))
        fields[1].setText('Beta')
        MainWindow.room_text_edited(window, fields[1])
        self.assertFalse(fields[1].property('roomDuplicate'))

    def test_duplicate_cannot_be_saved_while_being_edited(self):
        window = SimpleNamespace(rooms=[QLineEdit('Alpha'), QLineEdit(' alpha ')], log=MagicMock())
        with patch('paltalk_automation.main_window.settings.save_settings') as save:
            self.assertFalse(MainWindow.save_current_settings(window, announce=False))
            save.assert_not_called()

    def test_distinct_entries_are_not_cleared(self):
        fields = [QLineEdit('Alpha'), QLineEdit('Alphabet')]
        window = SimpleNamespace(rooms=fields, log=MagicMock(), save_current_settings=MagicMock())
        MainWindow.finish_room_edit(window, fields[1])
        self.assertEqual(fields[1].text(), 'Alphabet')
        window.save_current_settings.assert_not_called()


if __name__ == '__main__':
    unittest.main()
