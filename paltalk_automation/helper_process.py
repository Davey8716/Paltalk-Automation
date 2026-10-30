"""Shared helper process command construction."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def helper_command(module, *args):
    """Launch helper modules through the bundled entry point when frozen."""
    executable = sys.executable
    if getattr(sys, 'frozen', False):
        return [executable, '--helper', module, *args]
    if Path(executable).name.lower() == 'pythonw.exe':
        executable = str(Path(executable).with_name('python.exe'))
    modules = {
        'room_helper_process': 'room_opener.backend.room_helper_process',
        'camera_helper_process': 'camera_opener.backend.camera_helper_process',
        'chat_reader_process': 'admin_actions.backend.chat_reader_process',
        'mic_timer': 'mic_timer.backend.mic_timer',
    }
    return [executable, '-m', f'paltalk_automation.{modules[module]}', *args]


