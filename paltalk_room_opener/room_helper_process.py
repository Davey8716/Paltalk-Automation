"""Isolated room operations; communicate as newline-delimited JSON."""

import json
import sys

from .automation import open_rooms, restore_paltalk, room_states


def send(kind, value):
    sys.stdout.write(json.dumps({'kind': kind, 'value': value}, ensure_ascii=True) + '\n')
    sys.stdout.flush()


def main():
    action, names_json = sys.argv[1:3]
    names = json.loads(names_json)
    stage = 'room-state scan'
    try:
        if action == 'single':
            stage = 'restoring Paltalk'
            send('stage', stage)
            restore_paltalk()
        stage = 'room-state scan'
        send('stage', stage)
        states = room_states(names)
        if action == 'states':
            send('result', states)
            return
        if states is None or any(name not in states for name in names):
            send('message', 'Could not determine open room status.')
            send('result', -2)
            return
        names = [name for name in names if not states[name]]
        if not names:
            send('message', 'Room is already open; skipping.')
            send('result', -3)
            return
        stage = 'finding room tile'
        send('stage', stage)
        def update_stage(value):
            nonlocal stage
            stage = 'invoking room tile' if value == 'invoking' else value
            send('stage', stage)
        count = open_rooms(names, 5, lambda message: send('message', message), lambda: False, stage=update_stage)
        send('result', count)
    except Exception as exc:
        send('error', f'{stage}: {str(exc).splitlines()[0] or type(exc).__name__}')


if __name__ == '__main__':
    main()
