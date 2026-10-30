import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from paltalk_automation.main_window import RoomDragHandle, RoomNameField


class RoomDragHandleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_handle_drop_reorders_and_clears_target_highlight(self):
        reorder = MagicMock()
        source = RoomDragHandle(0, reorder)
        target = RoomDragHandle(2, reorder)
        event = MagicMock()
        event.source.return_value = source

        target.dragEnterEvent(event)
        self.assertTrue(target.property('dragHighlight'))
        event.acceptProposedAction.assert_called_once()
        target.dropEvent(event)
        reorder.assert_called_once_with(0, 2)
        self.assertFalse(target.property('dragHighlight'))
        event.setDropAction.assert_called_once_with(Qt.DropAction.CopyAction)
        event.accept.assert_called_once()

    def test_leave_clears_highlight_and_unrelated_drag_is_ignored(self):
        target = RoomDragHandle(1, MagicMock())
        event = MagicMock()
        event.source.return_value = RoomNameField(0, MagicMock())
        target.dragEnterEvent(event)
        target.dragLeaveEvent(event)
        self.assertFalse(target.property('dragHighlight'))
        unrelated = MagicMock()
        unrelated.source.return_value = None
        target.dragEnterEvent(unrelated)
        unrelated.acceptProposedAction.assert_not_called()


if __name__ == '__main__':
    unittest.main()
