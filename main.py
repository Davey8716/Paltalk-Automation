"""Main entry point for Paltalk Automation."""

import sys
from PySide6.QtWidgets import QApplication, QMessageBox

from paltalk_room_opener.main_window import MainWindow
from paltalk_room_opener.single_instance import SingleInstance


def main():
    instance = SingleInstance()
    try:
        app = QApplication(sys.argv)
        if instance.already_running:
            QMessageBox.information(None, 'Paltalk Automation', 'Paltalk Automation is already running.')
            return 0
        window = MainWindow()
        if not window.start_in_tray.isChecked() or window.tray_icon is None:
            window.show()
        return app.exec()
    finally:
        instance.close()


if __name__ == "__main__":
    sys.exit(main())
