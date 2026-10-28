"""Run camera monitoring outside the user-interface process."""

import json
import sys
import threading

from .camera_automation import watch_cameras


def send(kind, value):
    sys.stdout.write(json.dumps({'kind': kind, 'value': value}, ensure_ascii=True) + '\n')
    sys.stdout.flush()


def main():
    names = json.loads(sys.argv[1])
    lock = threading.Lock()

    def read_updates():
        nonlocal names
        for line in sys.stdin:
            try:
                updated = json.loads(line)
                if not isinstance(updated, list) or not all(isinstance(name, str) for name in updated):
                    continue
                with lock:
                    names = updated
            except (ValueError, TypeError):
                continue

    def current_names():
        with lock:
            return list(names)

    threading.Thread(target=read_updates, daemon=True).start()
    try:
        watch_cameras(names, lambda value: send('message', value), lambda: False,
                      lambda value: send('invoked', value), lambda value: send('failed', value),
                      lambda value: send('progress', value), current_names)
    except Exception as exc:
        send('error', str(exc) or type(exc).__name__)


if __name__ == '__main__':
    main()
