"""Persistent application settings."""

import json
import os
from pathlib import Path


APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "PaltalkRoomOpener"
LEGACY_DATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "PaltalkRoomOpener"
SETTINGS_PATH = APP_DATA_DIR / "room_names.json"
CAMERA_SETTINGS_PATH = APP_DATA_DIR / "camera_names.json"
ADMIN_SETTINGS_PATH = APP_DATA_DIR / "admin_actions.json"
APP_STATE_PATH = APP_DATA_DIR / "app_state.json"
RECENT_ROOMS_PATH = APP_DATA_DIR / "recently visited.json"


def migrate_legacy_settings():
    """Copy missing legacy settings once, leaving existing local files untouched."""
    marker = APP_DATA_DIR / '.roaming-migration-complete'
    if marker.exists():
        return
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ('room_names.json', 'camera_names.json', 'admin_actions.json',
                 'app_state.json', 'recent_rooms.json'):
        source = LEGACY_DATA_DIR / name
        target = APP_DATA_DIR / name
        if target.exists() or not source.is_file():
            continue
        data = source.read_bytes()
        try:
            output = target.open('xb')
        except FileExistsError:
            continue
        try:
            with output:
                output.write(data)
        except OSError:
            target.unlink(missing_ok=True)
            raise
    marker.touch()


def migrate_recent_history():
    """Copy the old recent-room history to its new filename once."""
    marker = APP_DATA_DIR / '.recent-history-migration-complete'
    if marker.exists():
        return
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    source = APP_DATA_DIR / 'recent_rooms.json'
    if source.is_file() and not RECENT_ROOMS_PATH.exists():
        data = source.read_bytes()
        try:
            output = RECENT_ROOMS_PATH.open('xb')
        except FileExistsError:
            pass
        else:
            try:
                with output:
                    output.write(data)
            except OSError:
                RECENT_ROOMS_PATH.unlink(missing_ok=True)
                raise
    marker.touch()


def load_recent_rooms():
    try:
        names = json.loads(RECENT_ROOMS_PATH.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return []
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError('Saved recent rooms must be a list of room names.')
    return names


def merge_recent_rooms(names):
    saved = load_recent_rooms()
    merged = []
    seen = set()
    for name in [*names, *saved]:
        if isinstance(name, str) and name.strip() and name not in seen:
            seen.add(name)
            merged.append(name)
    if merged != saved:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        RECENT_ROOMS_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8')
    return merged


def load_app_state():
    try:
        return json.loads(APP_STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_app_state(selected_tab=None, start_in_tray=None, recent_rooms_alphabetical=None):
    data = load_app_state()
    if selected_tab is not None:
        data['selected_tab'] = selected_tab
    if start_in_tray is not None:
        data['start_in_tray'] = start_in_tray
    if recent_rooms_alphabetical is not None:
        data['recent_rooms_alphabetical'] = recent_rooms_alphabetical
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    APP_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_camera_settings():
    try:
        return json.loads(CAMERA_SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load_admin_phrases():
    try:
        data = json.loads(ADMIN_SETTINGS_PATH.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return []
    phrases = data.get('banned_phrases') if isinstance(data, dict) else None
    if not isinstance(phrases, list) or any(not isinstance(phrase, str) for phrase in phrases):
        raise ValueError('Saved banned phrases must be a list of text phrases.')
    return phrases


def save_admin_phrases(phrases):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_SETTINGS_PATH.write_text(json.dumps({'banned_phrases': phrases}, indent=2, ensure_ascii=False), encoding='utf-8')


def save_camera_settings(names, start_on_paltalk, alphabetical=False):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CAMERA_SETTINGS_PATH.write_text(json.dumps({"usernames": names, "start_on_paltalk": start_on_paltalk, "alphabetical": alphabetical}, indent=2), encoding="utf-8")


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


def save_room_mode(mode):
    """Persist the mode without saving other unsaved room settings."""
    data = load_settings()
    data['mode'] = mode
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
