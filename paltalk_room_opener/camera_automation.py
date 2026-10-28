"""Read the visible On Cam list and invoke its matching camera controls."""

import ctypes
import json
import os
import subprocess
import tempfile
import time
from importlib import import_module
from pathlib import Path

from PIL import Image, ImageGrab, ImageOps, ImageDraw, ImageEnhance
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


class _ScanStopped(Exception):
    pass


def _ocr(image, stopped=lambda: False):
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as file:
        path = file.name
    try:
        image.save(path)
        script = Path(__file__).with_name('windows_ocr.ps1')
        process = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(script), path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + 15
        try:
            while True:
                if stopped():
                    raise _ScanStopped()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Windows OCR timed out.')
                try:
                    stdout, stderr = process.communicate(timeout=min(.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise RuntimeError('Windows OCR failed: ' + (stderr.strip() or 'unknown error'))
            return json.loads(stdout, strict=False)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    finally:
        os.unlink(path)


def _camera_state(image, x, y, width, height):
    """Paltalk currently draws available cameras blue and opened views green."""
    crop = image.crop((x, y, x + width, y + height)).convert('RGB')
    blue = green = 0
    pixels = crop.get_flattened_data() if hasattr(crop, 'get_flattened_data') else crop.getdata()
    for r, g, b in pixels:
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


def _badge_boxes(image, left, top, right, bottom):
    """Find compact, filled colored shapes; letter strokes are normally much thinner."""
    crop = image.crop((left, top, right, bottom)).convert('RGB')
    width, height = crop.size
    pixels = crop.load()
    colored = set()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if max(r, g, b) >= 120 and max(r, g, b) - min(r, g, b) >= 75:
                colored.add((x, y))
    boxes = []
    while colored:
        point = colored.pop()
        stack = [point]
        component = [point]
        while stack:
            x, y = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (x + dx, y + dy)
                    if neighbor in colored:
                        colored.remove(neighbor)
                        stack.append(neighbor)
                        component.append(neighbor)
        xs, ys = zip(*component)
        x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
        w, h = x1 - x0, y1 - y0
        if w >= 8 and h >= 8 and len(component) >= 45 and len(component) / (w * h) >= .4:
            boxes.append((left + x0, top + y0, left + x1, top + y1))
    return sorted(boxes)


def _row_words(lines, center, button_x, scale=1):
    words = []
    for line in lines:
        for word in line.get('words', []):
            item = {key: value / scale for key, value in word.items() if key != 'text'}
            item['text'] = word['text']
            if abs((item['top'] + item['bottom']) / 2 - center) <= 9 and item['right'] <= button_x:
                words.append(item)
    return sorted(words, key=lambda word: word['left'])


def _section_words(words, section):
    # Queue positions are separate OCR words to the left of the nickname.
    # Never strip digits joined to a nickname, such as 1SweeTart.
    if (section == 'Mic Queue' and len(words) > 1 and words[0]['text'].isdigit()
            and 0 <= words[0]['left'] <= 16
            and words[0]['right'] < words[1]['left']):
        return words[1:]
    return words


def _sections(lines, height):
    headings = []
    labels = (('micqueue', 'Mic Queue'), ('oncam', 'On Cam'),
              ('chatting', None), ('members', None))
    for line in lines:
        normalized = _normal(line['text'])
        for prefix, label in labels:
            if normalized.startswith(prefix):
                headings.append((line['top'], line['bottom'], label))
                break
    headings.sort(key=lambda heading: heading[0])
    for label in ('Mic Queue', 'On Cam'):
        if sum(heading[2] == label for heading in headings) > 1:
            raise RuntimeError(f'{label} heading is ambiguous.')
    sections = []
    for index, (_, bottom, label) in enumerate(headings):
        if label is not None:
            end = headings[index + 1][0] if index + 1 < len(headings) else height
            if bottom < end:
                sections.append((label, bottom, end))
    if not sections:
        raise RuntimeError('Mic Queue or On Cam heading is not visible or could not be read.')
    return sections


def _button_section(current, button_type, y, height, sections):
    if (current.ControlType != button_type or current.IsOffscreen or
            'MemberContentWidget' not in current.AutomationId):
        return None
    matching = [label for label, start, end in sections if y >= start and y + height <= end]
    return matching[0] if len(matching) == 1 else None


def _row_text(words, boundary=None):
    if not words:
        return None
    selected = []
    for word in words:
        if boundary is not None and word['right'] > boundary:
            if word['left'] < boundary:
                return None  # OCR combined text and badge; the boundary is uncertain.
            break
        selected.append(word['text'])
    return ' '.join(selected).strip() or None


def _readings(row):
    return (row[0],) if isinstance(row[0], str) else row[0]


def _match_rows(rows, names, target):
    """Return matching rows and whether any row also names another saved user."""
    configured = {_normal(name) for name in names}
    wanted = _normal(target)
    matches = []
    conflict = False
    for row in rows:
        found = {_normal(value) for value in _readings(row) if value} & configured
        if wanted in found:
            matches.append(row)
            if len(found) > 1:
                conflict = True
    return matches, conflict


class CameraScanner:
    def __init__(self):
        # Match UI Automation physical pixels to screenshots on scaled displays.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
        self.a = _uia()

    def scan(self):
        stopped = getattr(self, 'stopped', lambda: False)
        progress = getattr(self, 'progress', lambda stage: None)
        progress('finding the visible room')
        if stopped():
            raise _ScanStopped()
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
        progress('reading the room list')
        lines = _ocr(image, stopped)
        sections = _sections(lines, height)
        self.ocr_lines = [f"{label}: {line['text'].strip()}"
                          for label, start, end in sections for line in lines
                          if start < (line['top'] + line['bottom']) / 2 < end]
        buttons = []
        for e in member_list.FindAll(a.TreeScope.Descendants, a.Condition.TrueCondition):
            c = e.Current
            if c.ControlType != a.ControlType.Button or c.IsOffscreen or 'MemberContentWidget' not in c.AutomationId:
                continue
            b = c.BoundingRectangle
            x, y = int(b.X) - left, int(b.Y) - top
            bw, bh = int(b.Width), int(b.Height)
            if bw <= 0 or bh <= 0 or x < 0 or x + bw > width:
                continue
            section = _button_section(c, a.ControlType.Button, y, bh, sections)
            if section is None:
                continue
            buttons.append((y + bh / 2, _camera_state(image, x, y, bw, bh), e, x, section))
        # Find badge shapes after the first recognized word. Never cut through a
        # word: a merged word makes that row ambiguous instead.
        boundaries = {}
        source = image.convert('RGB')
        enhanced = source.copy()
        draw = ImageDraw.Draw(enhanced)
        for index, (center, _, _, button_x, section) in enumerate(buttons):
            words = _section_words(_row_words(lines, center, button_x), section)
            if not words:
                continue
            top = max(0, int(center - 10))
            bottom = min(height, int(center + 10))
            boxes = _badge_boxes(image, 0, top, button_x, bottom)
            badges = [box for box in boxes if box[0] >= words[0]['right'] + 1]
            if badges:
                boundary = badges[0][0]
                boundaries[index] = boundary
                background = source.getpixel((0, min(height - 1, int(center))))
                draw.rectangle((boundary, top, max(boundary, button_x - 1), bottom - 1), fill=background)
        # Use a single enlarged capture for all rows to avoid launching OCR once per name.
        scale = 2 if max(width, height) <= 2048 else 1
        color_image = enhanced
        enhanced = ImageOps.autocontrast(ImageOps.grayscale(color_image))
        enhanced = enhanced.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
        progress('reading enhanced names')
        enhanced_lines = _ocr(enhanced, stopped)
        # A differently processed color capture resolves cases where one pass
        # drops a word or confuses similar characters such as 1 and l.
        third_image = ImageEnhance.Contrast(color_image).enhance(1.5)
        third_image = third_image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
        progress('checking name readings')
        third_lines = _ocr(third_image, stopped)
        rows = []
        self.ocr_comparisons = []
        for index, (center, state, element, button_x, section) in enumerate(buttons):
            if sum(abs(other[0] - center) <= 18 for other in buttons) != 1:
                self.ocr_comparisons.append(f'{section} row at {center:.0f}: camera buttons overlap')
                continue
            boundary = boundaries.get(index)
            first = _row_text(_section_words(_row_words(lines, center, button_x), section), boundary)
            second = _row_text(_section_words(_row_words(enhanced_lines, center, button_x, scale), section), boundary)
            third = _row_text(_section_words(_row_words(third_lines, center, button_x, scale), section), boundary)
            readings = tuple(dict.fromkeys(value for value in (first, second, third) if value))
            if len(readings) != 1 or first is None:
                original_words = _row_words(lines, center, button_x)
                positions = [(word['text'], round(word['left'], 1), round(word['right'], 1))
                             for word in original_words]
                self.ocr_comparisons.append(
                    f'{section} row at {center:.0f}: original={first!r}, enhanced={second!r}, color={third!r}, '
                    f'badge boundary={boundary!r}, original word positions={positions!r}')
            if readings:
                rows.append((readings, state, element, center, section))
        return rows

    def open_if_available(self, name, stopped=lambda: False, configured_names=None):
        # A second complete capture and lookup ensures list reorderings do not reuse stale elements.
        room = getattr(self, 'room_identity', None)
        matches, conflict = _match_rows(self.scan(), configured_names or [name], name)
        if (stopped() or room != getattr(self, 'room_identity', None) or
                conflict or len(matches) != 1 or matches[0][1] != 'available'):
            return False
        getattr(self, 'progress', lambda stage: None)('opening a camera')
        matches[0][2].GetCurrentPattern(self.a.InvokePattern.Pattern).Invoke()
        getattr(self, 'progress', lambda stage: None)('camera invocation finished')
        return True


def watch_cameras(names, log, stopped, invoked=None, failed=None, progress=None):
    if invoked is None:
        invoked = log
    if failed is None:
        failed = log
    if progress is None:
        progress = lambda stage: None
    progress('starting camera scanner')
    scanner = CameraScanner()
    scanner.stopped = stopped
    scanner.progress = progress
    names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    last_error = None
    attempts = {}
    previous_room = None
    reported = {}
    diagnostic_reported = False
    while not stopped():
        try:
            rows = scanner.scan()
            if scanner.room_identity != previous_room:
                previous_room = scanner.room_identity
                attempts.clear()
                reported.clear()
                diagnostic_reported = False
                log('Monitoring the displayed room.')
            if last_error:
                log('Camera list is available again.')
                last_error = None
            for name in names:
                if stopped():
                    break
                matches, conflict = _match_rows(rows, names, name)
                if sum(_normal(other) == _normal(name) for other in names) != 1:
                    status = 'ambiguous configured username'
                elif len(matches) != 1 or conflict:
                    if conflict:
                        status = 'row matches multiple saved usernames'
                    elif len(matches) > 1:
                        status = 'username matches multiple rows'
                    else:
                        status = 'not visible or ambiguous'
                    if not diagnostic_reported:
                        read = ', '.join(repr(line) for line in scanner.ocr_lines) or '(none)'
                        detected = ', '.join(f'{row[4]}: {_readings(row)!r}' for row in rows) or '(none)'
                        log(f'Visible section text read by OCR: {read}.')
                        log(f'OCR lines matched to camera buttons: {detected}.')
                        if scanner.ocr_comparisons:
                            log('Unmatched OCR rows: ' + '; '.join(scanner.ocr_comparisons))
                        diagnostic_reported = True
                elif matches[0][1] == 'unknown':
                    status = 'camera icon not recognized'
                else:
                    status = matches[0][1]
                if reported.get(name) != status:
                    if status not in ('available', 'open'):
                        failed(f'{name}: {status}.')
                    reported[name] = status
                if status != 'available':
                    continue
                key = _normal(name)
                if time.monotonic() - attempts.get(key, 0) < 10:
                    continue
                attempts[key] = time.monotonic()
                if scanner.open_if_available(name, stopped, names):
                    invoked(f'Invoked camera button for {name}; check the video view to confirm it opened.')
                    # Let Paltalk finish opening the view before invoking another.
                    for _ in range(10):
                        if stopped():
                            break
                        time.sleep(.1)
                else:
                    failed(f'Skipped {name}: the row changed or could not be verified.')
        except _ScanStopped:
            break
        except Exception as exc:
            message = str(exc)
            if message != last_error:
                log(f'Camera watcher: {message}')
                last_error = message
        progress('waiting for the next scan')
        for _ in range(20):
            if stopped():
                break
            time.sleep(.1)
