import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from paltalk_room_opener.automation import _discovered_room_names
from paltalk_room_opener.main_window import MainWindow


class OtherRoomsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_only_verified_close_controls_are_discovered(self):
        def button(identifier, name='Room close'):
            return SimpleNamespace(Current=SimpleNamespace(AutomationId=identifier, Name=name))
        prefix = 'QApplication.mainWindow.QWidget.RoomItem_'
        valid = prefix + 'The Flirting Zone.RoomItem_The Flirting Zone_CloseButton'
        controls = [button(valid), button(valid), button(valid, 'Other close'),
                    button(prefix + 'Alpha.RoomItem_Beta_CloseButton'),
                    button('Room close: Unknown')]
        self.assertEqual(_discovered_room_names(controls), ['The Flirting Zone'])

    def test_rows_filter_all_saved_entries_and_follow_scan(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        window = SimpleNamespace(rooms=[QLineEdit(name) for name in ['One', 'Two', 'Three', 'Four', 'Five']],
                                 other_open_names=['Five', 'Extra', 'Extra', 'Another'],
                                 other_rooms_layout=layout, worker=None, close_room_worker=None,
                                 close_other_room=lambda name: None)
        MainWindow.update_other_rooms(window)
        self.assertEqual(layout.count(), 2)
        self.assertEqual([layout.itemAt(i).widget().findChild(QLineEdit).text() for i in range(layout.count())],
                         ['Extra', 'Another'])
        self.assertTrue(layout.itemAt(0).widget().findChild(QLineEdit).isReadOnly())
        window.other_open_names = ['Another']
        MainWindow.update_other_rooms(window)
        self.assertEqual(layout.count(), 1)
        self.assertEqual(layout.itemAt(0).widget().findChild(QLineEdit).text(), 'Another')

    def test_unavailable_scan_preserves_other_rooms(self):
        window = SimpleNamespace(worker=None, close_room_worker=None, room_states={'One': True},
                                 other_open_names=['Extra'], update_room_buttons=lambda: None)
        MainWindow.room_states_received(window, None)
        self.assertEqual(window.other_open_names, ['Extra'])
        self.assertEqual(window.room_states, {'One': True})

    def test_regular_mode_shows_open_inactive_rooms_and_vip_hides_them(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        rooms = [QLineEdit(name) for name in ['One', 'Two', 'Three', 'Four', 'Five']]
        for field in rooms[3:]:
            field.setProperty('roomAvailable', False)
        window = SimpleNamespace(rooms=rooms, other_open_names=['One', 'Four', 'Five', 'Extra'],
                                 other_rooms_layout=layout, worker=None, close_room_worker=None,
                                 close_other_room=lambda name: None)
        MainWindow.update_other_rooms(window)
        self.assertEqual([layout.itemAt(i).widget().findChild(QLineEdit).text() for i in range(layout.count())],
                         ['Four', 'Five', 'Extra'])
        for field in rooms[3:]:
            field.setProperty('roomAvailable', True)
        MainWindow.update_other_rooms(window)
        self.assertEqual([layout.itemAt(i).widget().findChild(QLineEdit).text() for i in range(layout.count())],
                         ['Extra'])


if __name__ == '__main__':
    unittest.main()
