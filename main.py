"""Main entry point for Paltalk Automation."""

import sys

from PySide6.QtWidgets import QApplication

from paltalk_room_opener.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
