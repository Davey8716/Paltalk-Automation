"""Read the visible On Cam list and invoke its matching camera controls."""

import ctypes
from ctypes import wintypes
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
    """Find compact colored, grey and outlined badges beside usernames."""
    crop = image.crop((left, top, right, bottom)).convert('RGB')
    width, height = crop.size
    pixels = crop.load()
    colored, grey, pale = set(), set(), set()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if max(r, g, b) >= 120 and max(r, g, b) - min(r, g, b) >= 75:
                colored.add((x, y))
            elif 65 <= min(r, g, b) and max(r, g, b) <= 190 and max(r, g, b) - min(r, g, b) <= 18:
                grey.add((x, y))
            elif 190 < min(r, g, b) and max(r, g, b) <= 230 and max(r, g, b) - min(r, g, b) <= 18:
                pale.add((x, y))
    boxes = []
    for pixels_to_check, kind in ((colored, 'colored'), (grey, 'grey'), (pale, 'pale')):
        while pixels_to_check:
            point = pixels_to_check.pop()
            stack = [point]
            component = [point]
            while stack:
                x, y = stack.pop()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        neighbor = (x + dx, y + dy)
                        if neighbor in pixels_to_check:
                            pixels_to_check.remove(neighbor)
                            stack.append(neighbor)
                            component.append(neighbor)
            xs, ys = zip(*component)
            x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
            w, h = x1 - x0, y1 - y0
            compact = kind == 'colored' or (w <= 20 and h <= 20 and .75 <= w / h <= 1.25)
            # Outlined icons have a thinner connected border than filled badges.
            points = set(component)
            border = sum((x, y) in points for x in range(x0 + 2, x1 - 2) for y in (y0, y1 - 1))
            outlined = (kind != 'colored' and w >= 12 and h >= 12 and len(component) >= 35
                        and len(component) / (w * h) >= .18 and border >= w)
            filled = kind != 'pale' and len(component) >= 45 and len(component) / (w * h) >= .4
            if w >= 8 and h >= 8 and compact and (outlined or filled):
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


def _camera_error_message(exc):
    message = str(exc).strip()
    if 'MS.Internal.Automation.UiaCoreApi' in message or '0x80004005' in message:
        return 'Paltalk controls are temporarily unavailable. Retrying.'
    return message.splitlines()[0].strip() if message else type(exc).__name__


def _match_rows(rows, names, target):
    """Return matching rows and whether any row also names another saved user."""
    configured = {_normal(name) for name in names}
    wanted = _normal(target)
    def punctuation_key(value):
        return value.replace('-', '_')

    matches = []
    conflict = False
    for row in rows:
        readings = {_normal(value) for value in _readings(row) if value}
        found = set()
        for reading in readings:
            if reading in configured:
                found.add(reading)
            else:
                found.update(name for name in configured
                             if punctuation_key(name) == punctuation_key(reading))
        if wanted in found:
            matches.append(row)
            if len(found) > 1:
                conflict = True
    return matches, conflict


def _portrait_clip_offset(monitor, member_right):
    """Return how far the member list extends past a portrait display."""
    if monitor.right - monitor.left >= monitor.bottom - monitor.top:
        return 0
    return max(0, int(member_right - monitor.right + 1)) if member_right > monitor.right else 0


def _reposition_clipped_portrait_window(window, member_right):
    """Move the window left just enough to expose a clipped member list."""
    hwnd = window.Current.NativeWindowHandle
    if not hwnd:
        return False
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    monitor = user32.MonitorFromWindow(hwnd, 2)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    bounds = wintypes.RECT()
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise RuntimeError('Could not identify the Paltalk display.')
    offset = _portrait_clip_offset(info.rcMonitor, member_right)
    if not offset:
        return False
    if not user32.GetWindowRect(hwnd, ctypes.byref(bounds)):
        raise RuntimeError('Could not determine the Paltalk window position.')
    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE permits moving a maximized window.
    if not user32.SetWindowPos(hwnd, None, bounds.left - offset, bounds.top,
                               bounds.right - bounds.left, bounds.bottom - bounds.top,
                               0x0010 | 0x0004):  # SWP_NOACTIVATE | SWP_NOZORDER
        raise RuntimeError('Could not move Paltalk to reveal the camera buttons.')
    return True


def _adjust_portrait_if_needed(scanner, window, rect, progress):
    if getattr(scanner, 'portrait_adjustment_enabled', lambda: True)():
        position = (window.Current.NativeWindowHandle, rect.X, rect.Y, rect.Width, rect.Height)
        if getattr(scanner, '_portrait_adjustment', None) == position:
            raise RuntimeError('Paltalk could not be moved far enough to reveal the camera buttons.')
        if _reposition_clipped_portrait_window(window, rect.X + rect.Width):
            scanner._portrait_adjustment = position
            progress('adjusting Paltalk window for portrait display')
            raise RuntimeError('Adjusted Paltalk to reveal camera buttons; retrying the scan.')
    scanner._portrait_adjustment = None


class CameraScanner:
    def __init__(self):
        # Match UI Automation physical pixels to screenshots on scaled displays.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
        self.a = _uia()

    def scan(self):
        try:
            return self._scan()
        except BaseException:
            self._ocr_cache = None
            raise

    def _scan(self):
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
        int32 = import_module('System').Int32
        windows = []
        for pid in pids:
            condition = a.AndCondition(
                a.PropertyCondition(a.AutomationElement.ProcessIdProperty, int32(pid)),
                a.PropertyCondition(a.AutomationElement.ClassNameProperty, 'qtctrl::WindowContainer'),
            )
            windows.extend(a.AutomationElement.RootElement.FindAll(a.TreeScope.Children, condition))
        lists = []
        for window in windows:
            elements = window.FindAll(a.TreeScope.Descendants,
                a.PropertyCondition(a.AutomationElement.ClassNameProperty,
                                    'ui::rooms::member_list::RoomMemberListWidget'))
            for element in elements:
                c = element.Current
                if not c.IsOffscreen:
                    rect = c.BoundingRectangle
                    if rect.Width > 0 and rect.Height > 0:
                        lists.append((window, element))
        if len(lists) != 1:
            raise RuntimeError('Display one room with its member list visible.')
        window, member_list = lists[0]
        self.room_identity = tuple(member_list.GetRuntimeId())
        rect = member_list.Current.BoundingRectangle
        _adjust_portrait_if_needed(self, window, rect, progress)
        left, top = int(rect.X), int(rect.Y)
        width, height = int(rect.Width), int(rect.Height)
        if width < 30 or height < 30 or width > 3000 or height > 4000:
            raise RuntimeError('Room member list has invalid screen bounds.')
        image = ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True)
        # Gather fresh controls before deciding whether the OCR results can be reused.
        controls = []
        for e in member_list.FindAll(a.TreeScope.Descendants,
                a.PropertyCondition(a.AutomationElement.ControlTypeProperty, a.ControlType.Button)):
            c = e.Current
            if c.ControlType != a.ControlType.Button or c.IsOffscreen or 'MemberContentWidget' not in c.AutomationId:
                continue
            b = c.BoundingRectangle
            x, y = int(b.X) - left, int(b.Y) - top
            bw, bh = int(b.Width), int(b.Height)
            if bw <= 0 or bh <= 0 or x < 0 or y < 0 or x + bw > width or y + bh > height:
                continue
            controls.append((x, y, bw, bh, e))
        geometry = tuple((x, y, bw, bh) for x, y, bw, bh, _ in controls)
        comparison = image.convert('RGB')
        mask = ImageDraw.Draw(comparison)
        for x, y, bw, bh in geometry:
            mask.rectangle((x, y, x + bw - 1, y + bh - 1), fill=(0, 0, 0))
        cache_key = (self.room_identity, width, height, geometry, comparison.tobytes())
        cache = getattr(self, '_ocr_cache', None)
        if cache is not None and cache['key'] == cache_key:
            self.ocr_lines = cache['ocr_lines']
            self.ocr_comparisons = cache['ocr_comparisons']
            return [(readings, _camera_state(image, *geometry[index]), controls[index][4], center, section)
                    for index, readings, center, section in cache['rows']]
        # A failed or interrupted refresh must never leave an older cache usable.
        self._ocr_cache = None
        progress('reading the room list')
        lines = _ocr(image, stopped)
        sections = _sections(lines, height)
        self.ocr_lines = [f"{label}: {line['text'].strip()}"
                          for label, start, end in sections for line in lines
                          if start < (line['top'] + line['bottom']) / 2 < end]
        buttons = []
        button_indices = []
        for index, (x, y, bw, bh, e) in enumerate(controls):
            section = _button_section(e.Current, a.ControlType.Button, y, bh, sections)
            if section is None:
                continue
            buttons.append((y + bh / 2, _camera_state(image, x, y, bw, bh), e, x, section))
            button_indices.append(index)
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
        cached_rows = []
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
                cached_rows.append((button_indices[index], readings, center, section))
        self._ocr_cache = {'key': cache_key, 'sections': sections, 'rows': cached_rows,
                           'ocr_lines': self.ocr_lines, 'ocr_comparisons': self.ocr_comparisons}
        return rows

    def open_if_available(self, name, stopped=lambda: False, configured_names=None):
        # A second complete capture and lookup ensures list reorderings do not reuse stale elements.
        room = getattr(self, 'room_identity', None)
        rows = self.scan()
        names = configured_names() if callable(configured_names) else configured_names
        matches, conflict = _match_rows(rows, names if names is not None else [name], name)
        if (stopped() or room != getattr(self, 'room_identity', None) or
                conflict or len(matches) != 1 or matches[0][1] != 'available'):
            return False
        getattr(self, 'progress', lambda stage: None)('opening a camera')
        matches[0][2].GetCurrentPattern(self.a.InvokePattern.Pattern).Invoke()
        getattr(self, 'progress', lambda stage: None)('camera invocation finished')
        return True


class ManualCameraTracker:
    """Match OCR candidates across scans only when they identify one row."""
    def __init__(self):
        self.previous = []
        self.context = None

    def reset(self):
        self.previous = []
        self.context = None

    def scan(self, rows, room, enabled, generation, names):
        if not enabled:
            self.reset()
            return []
        current = []
        for row in rows:
            readings = list(dict.fromkeys(value.strip() for value in _readings(row) if value and value.strip()))
            if readings and row[1] in ('available', 'open'):
                section = row[4] if len(row) > 4 else None
                current.append((readings, {_normal(value) for value in readings}, row[1], section))
        context = (room, generation)
        listed = {_normal(name).replace('-', '_') for name in names}
        opened = []
        if self.context == context:
            prompted_keys = set()
            for readings, keys, state, section in current:
                if state != 'open' or any(key.replace('-', '_') in listed for key in keys):
                    continue
                matches = [old for old in self.previous if old[3] == section and keys & old[1]]
                if len(matches) != 1 or matches[0][2] != 'available':
                    continue
                old = matches[0]
                if sum(other[3] == section and bool(other[1] & old[1]) for other in current) != 1:
                    continue
                if any(key.replace('-', '_') in listed for key in old[1]):
                    continue
                shared = keys & old[1]
                all_keys = keys | old[1]
                if all_keys & prompted_keys:
                    continue
                opened.append(next(value for value in readings if _normal(value) in shared))
                prompted_keys.update(all_keys)
        self.previous = current
        self.context = context
        return opened


def watch_cameras(names, log, stopped, invoked=None, failed=None, progress=None, current_names=None, live_status=None,
                  portrait_adjustment_enabled=None, manual_prompt_state=None, manual_opened=None):
    if invoked is None:
        invoked = log
    if failed is None:
        failed = log
    if progress is None:
        progress = lambda stage: None
    if live_status is None:
        live_status = lambda names: None
    progress('starting camera scanner')
    scanner = CameraScanner()
    scanner.portrait_adjustment_enabled = portrait_adjustment_enabled or (lambda: True)
    scanner.stopped = stopped
    scanner.progress = progress
    names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    last_error = None
    attempts = {}
    pending = {}
    previous_room = None
    reported = {}
    diagnostic_reported = False
    manual_tracker = ManualCameraTracker()
    while not stopped():
        retry_delay = .25
        try:
            if current_names is not None:
                names = list(dict.fromkeys(name.strip() for name in current_names() if name.strip()))
            active_keys = {_normal(name) for name in names}
            for key in list(pending):
                if key not in active_keys:
                    attempted_name, _, _ = pending.pop(key)
                    failed(f'{attempted_name}: camera opening could not be confirmed because the username was removed.')
            rows = scanner.scan()
            if manual_prompt_state is not None and manual_opened is not None:
                enabled, generation = manual_prompt_state()
                for detected_name in manual_tracker.scan(rows, scanner.room_identity, enabled, generation, names):
                    if not stopped():
                        manual_opened(detected_name)
            if scanner.room_identity != previous_room:
                for attempted_name, _, _ in pending.values():
                    failed(f'{attempted_name}: camera opening could not be confirmed because the room changed.')
                pending.clear()
                previous_room = scanner.room_identity
                attempts.clear()
                reported.clear()
                diagnostic_reported = False
                log('Monitoring the displayed room.')
            if last_error:
                log('Camera list is available again.')
                last_error = None
            live_names = []
            for name in names:
                if stopped():
                    break
                if current_names is not None:
                    latest_names = list(dict.fromkeys(value.strip() for value in current_names() if value.strip()))
                    if name not in latest_names:
                        continue
                else:
                    latest_names = names
                matches, conflict = _match_rows(rows, latest_names, name)
                if sum(_normal(other) == _normal(name) for other in latest_names) != 1:
                    status = 'ambiguous configured username'
                elif len(matches) != 1 or conflict:
                    if conflict:
                        status = 'row matches multiple saved usernames'
                    elif len(matches) > 1:
                        status = 'username matches multiple rows'
                    else:
                        status = 'not visible or ambiguous'
                    if not diagnostic_reported:
                        read = '\n\n'.join(scanner.ocr_lines) or '(none)'
                        detected = '\n\n'.join(f'{row[4]}: {_readings(row)!r}' for row in rows) or '(none)'
                        diagnostics = [f'Visible section text read by OCR:\n\n{read}',
                                       f'OCR lines matched to camera buttons:\n\n{detected}']
                        if scanner.ocr_comparisons:
                            diagnostics.append('Unmatched OCR rows:\n\n' + '\n\n'.join(scanner.ocr_comparisons))
                        log('\n\n' + '\n\n'.join(diagnostics) + '\n')
                        diagnostic_reported = True
                elif matches[0][1] == 'unknown':
                    status = 'camera icon not recognized'
                else:
                    status = matches[0][1]
                if status in ('available', 'open'):
                    live_names.append(name)
                if reported.get(name) != status:
                    if status not in ('available', 'open'):
                        failed(f'{name}: {status}.')
                    reported[name] = status
                key = _normal(name)
                if key in pending:
                    attempted_name, room, deadline = pending[key]
                    if status == 'open' and scanner.room_identity == room:
                        invoked(f'{attempted_name}: camera opening confirmed by the green open-view icon.')
                        del pending[key]
                    elif time.monotonic() >= deadline:
                        failed(f'{attempted_name}: camera button was invoked, but opening could not be confirmed.')
                        del pending[key]
                        attempts[key] = time.monotonic()
                    else:
                        continue
                if status != 'available':
                    continue
                if time.monotonic() - attempts.get(key, 0) < 2:
                    continue
                attempts[key] = time.monotonic()
                def name_removed():
                    return stopped() or (current_names is not None and name not in current_names())
                if scanner.open_if_available(name, name_removed, current_names or latest_names):
                    pending[key] = (name, scanner.room_identity, time.monotonic() + 5)
                    invoked(f'Invoked camera button for {name}; waiting for confirmation.')
                    # Let Paltalk finish opening the view before invoking another.
                    for _ in range(10):
                        if stopped():
                            break
                        time.sleep(.1)
                else:
                    failed(f'Skipped {name}: the row changed or could not be verified.')
            if not stopped():
                live_status(live_names)
        except _ScanStopped:
            break
        except Exception as exc:
            manual_tracker.reset()
            for attempted_name, _, _ in pending.values():
                failed(f'{attempted_name}: camera button was invoked, but opening could not be confirmed because the scan failed.')
            pending.clear()
            live_status([])
            message = _camera_error_message(exc)
            if message != last_error:
                log(f'Camera watcher: {message}')
                last_error = message
            retry_delay = 1
        progress('waiting for the next scan')
        for _ in range(round(retry_delay / .05)):
            if stopped():
                break
            time.sleep(.05)
