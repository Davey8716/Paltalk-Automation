"""Manage this user's Windows sign-in startup entry."""

from pathlib import Path
import subprocess
import sys
import winreg

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'Paltalk Automation'


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def set_startup(enabled):
    if enabled:
        if getattr(sys, 'frozen', False):
            command = [sys.executable]
        else:
            pythonw = Path(sys.executable).with_name('pythonw.exe')
            if not pythonw.exists():
                raise OSError('pythonw.exe was not found next to the current Python interpreter.')
            command = [str(pythonw), str(Path(__file__).resolve().parent.parent / 'main.py')]
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
