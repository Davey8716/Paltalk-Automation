"""Read the selected Paltalk room's chat through Windows UI Automation."""

from dataclasses import dataclass

import psutil

from .camera_automation import _uia


@dataclass(frozen=True)
class ChatMessage:
    sender: str
    text: str
    runtime_id: tuple


@dataclass(frozen=True)
class ChatSnapshot:
    room_id: tuple
    messages: tuple
    message_ids: tuple = ()


def associate_messages(rows):
    """Associate a message group only when it contains one unambiguous sender."""
    messages = []
    group = []

    def flush():
        names = [name for _, row_names, _, _ in group for name in row_names]
        if len(names) != 1 or not names[0].strip():
            return
        for _, _, text, runtime_id in group:
            if text:
                messages.append(ChatMessage(names[0], text, runtime_id))

    for kind, names, text, runtime_id in rows:
        if kind != 'message':
            flush()
            group = []
            continue
        group.append((kind, names, text, runtime_id))
    flush()
    return tuple(messages)


def read_selected_room_chat():
    """Return a snapshot of readable messages in the one displayed room.

    Room and message runtime IDs identify UI elements only for their current
    lifetime; callers must not treat them as permanent message identifiers.
    """
    a = _uia()
    pids = {p.info['pid'] for p in psutil.process_iter(['pid', 'name'])
            if (p.info.get('name') or '').lower() == 'paltalk.exe'}
    if not pids:
        raise RuntimeError('Paltalk is not running.')
    views = []
    windows = a.AutomationElement.RootElement.FindAll(a.TreeScope.Children, a.Condition.TrueCondition)
    for window in windows:
        if window.Current.ProcessId not in pids:
            continue
        if window.Current.ClassName != 'qtctrl::WindowContainer':
            continue
        for element in window.FindAll(a.TreeScope.Descendants, a.Condition.TrueCondition):
            c = element.Current
            if c.ClassName == 'ui::chatlog::ChatlogView' and not c.IsOffscreen:
                rect = c.BoundingRectangle
                if rect.Width > 0 and rect.Height > 0:
                    views.append(element)
    if len(views) != 1:
        raise RuntimeError('Display exactly one room with its chat visible.')
    view = views[0]
    containers = [e for e in view.FindAll(a.TreeScope.Children, a.Condition.TrueCondition)
                  if e.Current.ClassName == 'QWidget']
    if len(containers) != 1:
        raise RuntimeError('Could not identify the room chat message list.')
    rows = []
    message_ids = []
    for row in containers[0].FindAll(a.TreeScope.Children, a.Condition.TrueCondition):
        if row.Current.ClassName != 'ui::chatlog::TextMessageWidget':
            rows.append(('other', (), '', ()))
            continue
        runtime_id = tuple(row.GetRuntimeId())
        message_ids.append(runtime_id)
        names, texts = [], []
        has_username_widget = False
        for child in row.FindAll(a.TreeScope.Descendants, a.Condition.TrueCondition):
            c = child.Current
            if c.ClassName == 'ui::chatlog::UsernameWidget':
                has_username_widget = True
            if c.ClassName == 'QLabel' and '.ui::chatlog::UsernameWidget.' in (c.AutomationId or '') and c.Name:
                names.append(c.Name)
            elif c.ClassName == 'QTextBrowser':
                pattern = child.GetCurrentPattern(a.TextPattern.Pattern)
                texts.append(pattern.DocumentRange.GetText(-1))
        # A missing or ambiguous text widget should not lend its sender to later rows.
        if len(texts) != 1:
            rows.append(('other', (), '', ()))
            continue
        if has_username_widget and not names:
            names.append('')
        rows.append(('message', tuple(names), texts[0], runtime_id))
    return ChatSnapshot(tuple(view.GetRuntimeId()), associate_messages(rows), tuple(message_ids))
