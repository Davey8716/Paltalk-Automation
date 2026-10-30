"""Isolated room operations; communicate as newline-delimited JSON."""

import json
import sys

from paltalk_automation.room_opener.backend.automation import close_room, navigate_my_rooms, open_rooms, restore_paltalk, room_states, recently_visited_rooms


def send(kind, value):
    sys.stdout.write(json.dumps({'kind': kind, 'value': value}, ensure_ascii=True) + '\n')
    sys.stdout.flush()


def main():
    action, names_json = sys.argv[1:3]
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 5
    names = json.loads(names_json)
    stage = 'room-state scan'
    try:
        if action in ('recent', 'recent_background'):
            stage = 'reading recently visited rooms'
            send('stage', stage)
            send('result', recently_visited_rooms(expand=action == 'recent'))
            return
        if action in ('single', 'automatic'):
            stage = 'restoring Paltalk'
            send('stage', stage)
            restore_paltalk()
        stage = 'room-state scan'
        send('stage', stage)
        states = room_states(names, include_open_names=True) if action == 'states' else room_states(names)
        if action == 'states':
            send('result', states)
            return
        if states is None or any(name not in states for name in names):
            send('message', 'Could not determine open room status.')
            send('result', -2)
            return
        if action == 'single' and states[names[0]]:
            stage = 'closing room'
            send('stage', stage)
            close_room(names[0], lambda message: send('message', message))
            send('result', 0)
            return
        for name in names:
            if states[name]:
                send('message', f'Already open, skipping room: {name}')
        names = [name for name in names if not states[name]]
        if not names:
            send('message', 'All configured rooms are already open.')
            send('result', -3)
            return
        stage = 'opening My Rooms'
        send('stage', stage)
        navigate_my_rooms()
        stage = 'finding room tile'
        send('stage', stage)
        def update_stage(value):
            nonlocal stage
            stage = 'invoking room tile' if value == 'invoking' else value
            send('stage', stage)
        count = open_rooms(names, delay, lambda message: send('message', message), lambda: False, stage=update_stage)
        send('result', count)
    except Exception as exc:
        send('error', f'{stage}: {str(exc).splitlines()[0] or type(exc).__name__}')


if __name__ == '__main__':
    main()
