"""Main entry point for Paltalk Automation."""

import sys
from PySide6.QtWidgets import QApplication

from paltalk_room_opener.main_window import MainWindow
from paltalk_room_opener.single_instance import SingleInstance


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--helper':
        # Explicit imports also let PyInstaller discover every helper module.
        from paltalk_room_opener import camera_helper_process, chat_reader_process, mic_timer, room_helper_process
        helpers = {module.__name__.rsplit('.', 1)[-1]: module.main for module in (
            camera_helper_process, chat_reader_process, mic_timer, room_helper_process,
        )}
        helper = helpers.get(sys.argv[2])
        if helper is None:
            return 2
        sys.argv = [sys.argv[0], *sys.argv[3:]]
        helper()
        return 0
    instance = SingleInstance()
    try:
        app = QApplication(sys.argv)
        if instance.already_running:
            return 0
        window = MainWindow()
        if not window.start_in_tray.isChecked() or window.tray_icon is None:
            window.show()
        return app.exec()
    finally:
        instance.close()


if __name__ == "__main__":
    sys.exit(main())
