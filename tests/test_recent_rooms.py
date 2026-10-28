import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QListWidget, QPushButton, QWidget

from paltalk_room_opener import settings
from paltalk_room_opener.main_window import MainWindow
from paltalk_room_opener.worker import RecentRoomsWorker
from paltalk_room_opener.automation import _recent_tiles


class RecentRoomsTests(unittest.TestCase):
    def test_alphabetical_toggle_updates_dialog_in_both_directions(self):
        app = QApplication.instance() or QApplication([])
        window = QWidget()
        window.recent_rooms_worker = SimpleNamespace(automatic=False)
        window.log = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', path), \
                 patch.object(settings, 'RECENT_ROOMS_PATH', path / 'recent_rooms.json'), \
                 patch.object(settings, 'APP_STATE_PATH', path / 'app_state.json'):
                def check_dialog(dialog):
                    rooms = dialog.findChild(QListWidget)
                    button = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Alphabetical')
                    displayed = lambda: [rooms.item(i).text() for i in range(rooms.count())]
                    self.assertEqual(displayed(), ['zeta', 'Alpha'])
                    button.click()
                    self.assertEqual(displayed(), ['Alpha', 'zeta'])
                    self.assertEqual(settings.load_recent_rooms(), ['Alpha', 'zeta'])
                    button.click()
                    self.assertEqual(displayed(), ['zeta', 'Alpha'])
                with patch.object(QDialog, 'exec', check_dialog):
                    MainWindow.recent_rooms_received(window, ['zeta', 'Alpha'], '')

    def test_history_merges_new_rooms_and_keeps_older_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', path), \
                 patch.object(settings, 'RECENT_ROOMS_PATH', path / 'recent_rooms.json'), \
                 patch.object(settings, 'APP_STATE_PATH', path / 'app_state.json'):
                self.assertEqual(settings.merge_recent_rooms(['Alpha', 'Beta', 'Alpha']), ['Alpha', 'Beta'])
                self.assertEqual(settings.merge_recent_rooms(['Gamma', 'Alpha']), ['Gamma', 'Alpha', 'Beta'])
                self.assertEqual(settings.merge_recent_rooms([]), ['Gamma', 'Alpha', 'Beta'])
                self.assertEqual(settings.load_recent_rooms(), ['Gamma', 'Alpha', 'Beta'])

    def test_alphabetical_history_is_saved_and_stays_sorted_on_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(settings, 'APP_DATA_DIR', path), \
                 patch.object(settings, 'RECENT_ROOMS_PATH', path / 'recent_rooms.json'), \
                 patch.object(settings, 'APP_STATE_PATH', path / 'app_state.json'):
                settings.merge_recent_rooms(['zeta', 'Alpha'])
                self.assertEqual(settings.sort_recent_rooms(), ['Alpha', 'zeta'])
                self.assertEqual(json.loads(settings.RECENT_ROOMS_PATH.read_text(encoding='utf-8')), ['Alpha', 'zeta'])
                settings.save_app_state(recent_rooms_alphabetical=True)
                self.assertEqual(settings.merge_recent_rooms(['beta', 'zeta']), ['Alpha', 'beta', 'zeta'])
                self.assertEqual(settings.load_recent_rooms(), ['Alpha', 'beta', 'zeta'])
                settings.save_app_state(recent_rooms_alphabetical=False)
                self.assertEqual(settings.merge_recent_rooms(['zeta']), ['zeta', 'Alpha', 'beta'])

    def test_invalid_saved_history_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recent_rooms.json'
            path.write_text(json.dumps({'invalid': True}), encoding='utf-8')
            with patch.object(settings, 'RECENT_ROOMS_PATH', path):
                with self.assertRaises(ValueError):
                    settings.merge_recent_rooms(['Alpha'])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'invalid': True})

    def test_background_scan_saves_rooms_without_showing_a_dialog(self):
        window = SimpleNamespace(recent_rooms_worker=SimpleNamespace(automatic=True), log=MagicMock())
        with patch.object(settings, 'merge_recent_rooms') as merge:
            MainWindow.recent_rooms_received(window, ['Alpha'], '')
            MainWindow.recent_rooms_received(window, [], 'not visible')
        merge.assert_called_once_with(['Alpha'])

    def test_background_worker_uses_non_expanding_helper(self):
        worker = RecentRoomsWorker(automatic=True)
        results = []
        worker.result.connect(lambda names, error: results.append((names, error)))
        with patch('paltalk_room_opener.worker.run_room_helper', return_value=['Alpha']) as helper:
            worker.run()
        self.assertEqual(helper.call_args.args[0], 'recent_background')
        self.assertEqual(results, [(['Alpha'], '')])

    def test_collects_tiles_by_position_when_tree_order_differs(self):
        class Collection(list):
            @property
            def Count(self):
                return len(self)
        class Element:
            def __init__(self, kind, name='', descendants=(), y=0):
                self.Current = SimpleNamespace(ClassName=kind, Name=name,
                                               BoundingRectangle=SimpleNamespace(X=0, Y=y, Width=100, Height=10))
                self.descendants = descendants
            def Equals(self, other):
                return self is other
            def FindAll(self, scope, condition):
                return Collection(item for item in self.descendants if item.Current.ClassName == condition)
        a = SimpleNamespace(TreeScope=SimpleNamespace(Descendants=1),
                            AutomationElement=SimpleNamespace(ClassNameProperty=1),
                            PropertyCondition=lambda prop, value: value)
        header = Element('ui::rooms::ClosableListWidget', y=20)
        tile = lambda name, y: Element('ui::rooms::RoomTiles', name, y=y)
        children = [tile('Before', 0), header, Element('separator'),
                    Element('ui::rooms::ClosableListWidget', y=80), tile('Gamma', 60),
                    Element('wrapper', descendants=[tile('Beta', 50)]), tile('Alpha', 40),
                    tile('Other section', 90)]
        self.assertEqual(_recent_tiles(a, children, header), ['Alpha', 'Beta', 'Gamma'])


if __name__ == '__main__':
    unittest.main()
