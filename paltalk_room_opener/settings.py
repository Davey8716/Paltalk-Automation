"""Persistent application settings."""

import json
import os
from pathlib import Path


APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "PaltalkRoomOpener"
SETTINGS_PATH = APP_DATA_DIR / "room_names.json"
CAMERA_SETTINGS_PATH = APP_DATA_DIR / "camera_names.json"
APP_STATE_PATH = APP_DATA_DIR / "app_state.json"


def load_app_state():
    try:
        return json.loads(APP_STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_app_state(selected_tab):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    APP_STATE_PATH.write_text(json.dumps({"selected_tab": selected_tab}, indent=2), encoding="utf-8")


def load_camera_settings():
    try:
        return json.loads(CAMERA_SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_camera_settings(names, start_on_paltalk):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CAMERA_SETTINGS_PATH.write_text(json.dumps({"usernames": names, "start_on_paltalk": start_on_paltalk}, indent=2), encoding="utf-8")


def load_settings():
    """Return saved settings, or an empty mapping when none have been saved."""
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_settings(rooms, delay, mode, open_on_paltalk_start):
    """Save the five room entries and opening preferences."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "rooms": {f"room_{index}": room for index, room in enumerate(rooms, start=1)},
        "delay": delay,
        "mode": mode,
        "open_on_paltalk_start": open_on_paltalk_start,
    }
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
