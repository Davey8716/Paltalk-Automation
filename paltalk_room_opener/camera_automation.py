"""Read the visible On Cam list and invoke its matching camera controls."""

import ctypes
import json
import os
import subprocess
import tempfile
import time
from importlib import import_module
from pathlib import Path

from PIL import ImageGrab
import psutil


def _uia():
    try:
        clr = import_module('clr')
    except ModuleNotFoundError as exc:
        if exc.name != 'clr':
            raise
        raise RuntimeError('pythonnet is missing. Install the project requirements in the Python environment used to launch the app.') from exc
    root = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET' / 'assembly' / 'GAC_MSIL'
    for name in ('UIAutomationClient', 'UIAutomationTypes'):
        paths = sorted((root / name).glob(f'*/{name}.dll'))
        clr.AddReference(str(paths[-1]) if paths else name)
    return import_module('System.Windows.Automation')


def _ocr(image):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as file:
        path = file.name
    try:
        image.save(path)
        script = Path(__file__).with_name('windows_ocr.ps1')
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(script), path], capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            raise RuntimeError('Windows OCR failed: ' + (result.stderr.strip() or 'unknown error'))
        return json.loads(result.stdout, strict=False)
    finally:
        os.unlink(path)


def _camera_state(image, x, y, width, height):
    """Paltalk currently draws available cameras blue and opened views green."""
    crop = image.crop((x, y, x + width, y + height)).convert('RGB')
    blue = green = 0
    for r, g, b in crop.getdata():
        if b > 130 and b > r * 1.3 and b > g * 1.05:
            blue += 1
        if g > 110 and g > r * 1.35 and g > b * 1.2:
            green += 1
    if blue >= 8 and green < 5:
        return 'available'
    if green >= 8 and blue < 5:
        return 'open'
    return 'unknown'


def _normal(value):
    # Windows OCR sometimes inserts spaces inside a single displayed username.
    return ''.join(value.casefold().split())


class CameraScanner:
    def __init__(self):
        # Match UI Automation physical pixels to screenshots on scaled displays.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
        self.a = _uia()

    def scan(self):
        a = self.a
        pids = {p.info['pid'] for p in psutil.process_iter(['pid', 'name'])
                if (p.info.get('name') or '').lower() == 'paltalk.exe'}
        if not pids:
            raise RuntimeError('Paltalk is not running.')
        windows = a.AutomationElement.RootElement.FindAll(a.TreeScope.Children, a.Condition.TrueCondition)
        lists = []
        for window in windows:
            if window.Current.ProcessId not in pids or window.Current.ClassName != 'qtctrl::WindowContainer':
                continue
            elements = window.FindAll(a.TreeScope.Descendants, a.Condition.TrueCondition)
            for element in elements:
                c = element.Current
                if c.ClassName == 'ui::rooms::member_list::RoomMemberListWidget' and not c.IsOffscreen:
                    rect = c.BoundingRectangle
                    if rect.Width > 0 and rect.Height > 0:
                        lists.append(element)
        if len(lists) != 1:
            raise RuntimeError('Display one room with its member list visible.')
        member_list = lists[0]
        self.room_identity = tuple(member_list.GetRuntimeId())
        rect = member_list.Current.BoundingRectangle
        left, top = int(rect.X), int(rect.Y)
        width, height = int(rect.Width), int(rect.Height)
        if width < 30 or height < 30 or width > 3000 or height > 4000:
            raise RuntimeError('Room member list has invalid screen bounds.')
        image = ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True)
        lines = _ocr(image)
        headers = [line for line in lines if _normal(line['text']).startswith('oncam')]
        if len(headers) != 1:
            raise RuntimeError('On Cam heading is not visible or could not be read.')
        start = headers[0]['bottom']
        endings = [line['top'] for line in lines if line['top'] > start and
                   _normal(line['text']).startswith(('chatting', 'members'))]
        end = min(endings) if endings else height
        buttons = []
        for e in member_list.FindAll(a.TreeScope.Descendants, a.Condition.TrueCondition):
            c = e.Current
            if c.ControlType != a.ControlType.Button or c.IsOffscreen or 'MemberContentWidget' not in c.AutomationId:
                continue
            b = c.BoundingRectangle
            x, y = int(b.X) - left, int(b.Y) - top
            bw, bh = int(b.Width), int(b.Height)
            if bw <= 0 or bh <= 0 or x < 0 or y < start or x + bw > width or y + bh > end:
                continue
            buttons.append((y + bh / 2, _camera_state(image, x, y, bw, bh), e))
        rows = []
        for line in lines:
            center = (line['top'] + line['bottom']) / 2
            if not start < center < end:
                continue
            matching = [b for b in buttons if abs(b[0] - center) <= 9]
            if len(matching) == 1:
                rows.append((line['text'].strip(), matching[0][1], matching[0][2], center))
        return rows

    def open_if_available(self, name, stopped=lambda: False):
        # A second complete capture and lookup ensures list reorderings do not reuse stale elements.
        matches = [row for row in self.scan() if _normal(row[0]) == _normal(name)]
        if stopped() or len(matches) != 1 or matches[0][1] != 'available':
            return False
        matches[0][2].GetCurrentPattern(self.a.InvokePattern.Pattern).Invoke()
        return True


def watch_cameras(names, log, stopped):
    scanner = CameraScanner()
    names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    last_error = None
    attempts = {}
    previous_room = None
    reported = {}
    while not stopped():
        try:
            rows = scanner.scan()
            if scanner.room_identity != previous_room:
                previous_room = scanner.room_identity
                attempts.clear()
                reported.clear()
                log('Monitoring the displayed room.')
            if last_error:
                log('Camera list is available again.')
                last_error = None
            for name in names:
                if stopped():
                    break
                matches = [row for row in rows if _normal(row[0]) == _normal(name)]
                if sum(_normal(other) == _normal(name) for other in names) != 1:
                    status = 'ambiguous configured username'
                elif len(matches) != 1:
                    status = 'not visible or ambiguous'
                elif matches[0][1] == 'unknown':
                    status = 'camera icon not recognized'
                else:
                    status = matches[0][1]
                if reported.get(name) != status:
                    if status not in ('available', 'open'):
                        log(f'{name}: {status}.')
                    reported[name] = status
                if status != 'available':
                    continue
                key = _normal(name)
                if time.monotonic() - attempts.get(key, 0) < 10:
                    continue
                attempts[key] = time.monotonic()
                if scanner.open_if_available(name, stopped):
                    log(f'Invoked camera button for {name}; check the video view to confirm it opened.')
                else:
                    log(f'Skipped {name}: the row changed or could not be verified.')
        except Exception as exc:
            message = str(exc)
            if message != last_error:
                log(f'Camera watcher: {message}')
                last_error = message
        for _ in range(20):
            if stopped():
                break
            time.sleep(.1)
