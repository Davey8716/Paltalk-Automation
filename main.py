"""Main entry point for Paltalk Automation."""

import sys
import importlib.util
import subprocess
from pathlib import Path


def use_project_environment():
    """Use the installed project dependencies if launched with another Python."""
    if importlib.util.find_spec('clr') is not None:
        return
    project = Path(__file__).resolve().parent
    environment = project / '.venv'
    if Path(sys.prefix).resolve() == environment.resolve():
        return
    executable = environment / 'Scripts' / ('pythonw.exe' if Path(sys.executable).stem.lower() == 'pythonw' else 'python.exe')
    if executable.is_file():
        subprocess.Popen([str(executable), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=str(project))
        sys.exit(0)


use_project_environment()

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
        window.show()
        return app.exec()
    finally:
        instance.close()


if __name__ == "__main__":
    sys.exit(main())
