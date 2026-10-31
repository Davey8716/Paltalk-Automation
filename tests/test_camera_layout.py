import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QApplication

from paltalk_automation.camera_opener.ui_tabs.camera_name_list import CameraNameList
from paltalk_automation.main_window import MainWindow


class CameraLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_expansion_restore_and_manual_resize(self):
        class Window:
            _camera_original_size = None
            _camera_expanded_size = None
            current = QSize(1000, 900)
            def size(self): return QSize(self.current)
            def width(self): return self.current.width()
            def height(self): return self.current.height()
            def resize(self, width, height=None):
                self.current = QSize(width) if height is None else QSize(width, height)
            def screen(self): return SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 1920, 1000))
            def frameGeometry(self): return QRect(0, 0, self.width(), self.height())
            def y(self): return 0
            move = MagicMock()
        window = Window()
        MainWindow.resize_for_camera_tab(window, 1)
        self.assertEqual(window.size(), QSize(1880, 900))
        MainWindow.resize_for_camera_tab(window, 0)
        self.assertEqual(window.size(), QSize(1000, 900))
        MainWindow.resize_for_camera_tab(window, 1)
        window.resize(1200, 800)
        MainWindow.resize_for_camera_tab(window, 0)
        self.assertEqual(window.size(), QSize(1200, 800))

    def test_large_username_list_scrolls_on_narrow_layout(self):
        names = CameraNameList()
        names.resize(450, 842)
        names.addItems([f'User_{i}' for i in range(200)])
        names.show()
        self.app.processEvents()
        self.assertEqual(names.gridSize().height(), 20)
        self.assertGreater(names.horizontalScrollBar().maximum(), 0)
        names.scrollToItem(names.item(199))
        self.app.processEvents()
        self.assertTrue(names.viewport().rect().intersects(names.visualItemRect(names.item(199))))
        names.close()


if __name__ == '__main__':
    unittest.main()
