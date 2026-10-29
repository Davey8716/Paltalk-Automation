"""Read the visible Talking Now section using the existing room-list OCR."""

import json
import sys
import ctypes

import psutil
from PIL import Image, ImageGrab

from .camera_automation import _badge_boxes, _ocr, _row_text, _uia, _normal


class MicTimeTracker:
    """Track confirmed speakers by room, counting only observed intervals."""

    def __init__(self):
        self.rooms = {}
        self.room = None
        self.candidate = None
        self.candidate_since = None
        self.last_sample = None
        self.last_report = None

    def pause(self):
        self.room = None
        self.candidate = None
        self.last_sample = None
        self.last_report = None

    def observe(self, room, name, now):
        messages = []
        if room != self.room:
            if self.room is not None:
                previous = self.rooms.get(self.room)
                if previous and previous['name']:
                    messages.append(f"Mic timer: room changed; paused {previous['name']} at approximately {int(previous['elapsed'])} seconds.")
            self.room = room
            self.candidate = None
            self.last_sample = None
            self.last_report = None
        state = self.rooms.setdefault(room, {'name': None, 'elapsed': 0.0})
        key = name.casefold()
        if self.candidate != key:
            self.candidate = key
            self.candidate_since = now
            self.last_sample = None
            return messages
        previous_key = (state['name'] or '').casefold()
        if key != previous_key:
            if state['name']:
                messages.append(f"Mic timer: {state['name']} finished after approximately {int(state['elapsed'])} observed seconds.")
            state['name'] = name or None
            state['elapsed'] = 0.0
            self.last_report = None
            if name:
                messages.append(f'Mic timer: {name} started talking.')
            self.last_sample = self.candidate_since
        elif self.last_sample is None:
            self.last_sample = self.candidate_since
            if name and state['elapsed']:
                messages.append(f"Mic timer: resumed {state['name']} at approximately {int(state['elapsed'])} seconds.")
        if state['name']:
            state['elapsed'] += now - self.last_sample
            self.last_sample = now
            if self.last_report is None or now - self.last_report >= 15:
                messages.append(f"Mic timer: {state['name']} — approximately {int(state['elapsed'])} seconds on mic.")
                self.last_report = now
        return messages


def talking_now(lines, image=None):
    headings = [i for i, line in enumerate(lines) if _normal(line['text']).startswith('talkingnow')]
    if len(headings) != 1:
        raise ValueError('Talking Now heading is not visible or is ambiguous.')
    start = headings[0] + 1
    end = next((i for i in range(start, len(lines))
                if _normal(lines[i]['text']).startswith(('micqueue', 'oncam', 'chatting', 'members'))), None)
    if end is None:
        raise ValueError('The end of the Talking Now section is not visible.')
    rows = lines[start:end]
    if not rows:
        return ''
    if len(rows) != 1:
        raise ValueError('The Talking Now section could not be read confidently.')
    row = rows[0]
    word_data = row.get('words', [])
    if image is not None and word_data:
        top = max(0, int(row['top']) - 5)
        bottom = min(image.height, int(row['bottom']) + 5)
        boxes = _badge_boxes(image, 0, top, image.width, bottom)
        first_right = word_data[0]['right']
        boundary = min((box[0] for box in boxes if box[0] >= first_right + 1), default=None)
        if boundary is not None:
            value = _row_text(word_data, boundary)
            if not value:
                raise ValueError('The speaker name overlaps a badge and could not be read confidently.')
            return value
    words = [word['text'] for word in word_data]
    while len(words) > 1 and words[-1].isdigit():
        words.pop()
    name = ' '.join(words).strip()
    if not name:
        raise ValueError('The current speaker could not be read confidently.')
    return name


def scan():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    a = _uia()
    pids = {p.info['pid'] for p in psutil.process_iter(['pid', 'name'])
            if (p.info.get('name') or '').lower() == 'paltalk.exe'}
    if not pids:
        raise RuntimeError('Paltalk is not running.')
    lists = []
    try:
        windows = a.AutomationElement.RootElement.FindAll(a.TreeScope.Children, a.Condition.TrueCondition)
    except Exception as exc:
        raise RuntimeError('Could not inspect the desktop for Paltalk windows.') from exc
    condition = a.PropertyCondition(a.AutomationElement.ClassNameProperty,
                                    'ui::rooms::member_list::RoomMemberListWidget')
    failed_windows = 0
    for window in windows:
        try:
            if window.Current.ProcessId not in pids or window.Current.ClassName != 'qtctrl::WindowContainer':
                continue
            for element in window.FindAll(a.TreeScope.Descendants, condition):
                c = element.Current
                if c.IsOffscreen:
                    continue
                rect = c.BoundingRectangle
                if 30 <= rect.Width <= 3000 and 30 <= rect.Height <= 4000:
                    lists.append((element, window.Current.BoundingRectangle))
        except Exception:
            failed_windows += 1
    if len(lists) != 1:
        if not lists and failed_windows:
            raise RuntimeError('Paltalk did not respond to the room scan. Keep the room visible; retrying.')
        raise RuntimeError('Display one room with its member list visible and unobscured.')
    element, window_rect = lists[0]
    r = element.Current.BoundingRectangle
    x, y, width, height = int(r.X), int(r.Y), int(r.Width), int(r.Height)
    # Talking Now can sit above the member-list widget, so include the area
    # above it, bounded by the Paltalk window, as well as the list itself.
    top = max(int(window_rect.Y), y - 220)
    image = ImageGrab.grab(bbox=(x, top, x + width, y + height), all_screens=True)
    lines = _ocr(image)
    try:
        speaker = talking_now(lines, image)
    except ValueError as first_error:
        enlarged = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        try:
            speaker = talking_now(_ocr(enlarged), enlarged)
        except ValueError:
            preview = ', '.join(repr(line['text'][:60]) for line in lines[:6]) or '(no text)'
            raise ValueError(f'{first_error} OCR saw: {preview}.') from None
    return {'room': list(element.GetRuntimeId()), 'speaker': speaker}


def main():
    try:
        print(json.dumps(scan(), ensure_ascii=True))
    except Exception as exc:
        message = str(exc).splitlines()[0].strip() or type(exc).__name__
        print(json.dumps({'error': message}))


if __name__ == '__main__':
    main()
