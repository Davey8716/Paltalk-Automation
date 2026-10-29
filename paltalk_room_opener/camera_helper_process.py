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
    portrait_adjustment = json.loads(sys.argv[2]) if len(sys.argv) > 2 else True
    lock = threading.Lock()

    def read_updates():
        nonlocal names, portrait_adjustment
        for line in sys.stdin:
            try:
                updated = json.loads(line)
                with lock:
                    if isinstance(updated, list) and all(isinstance(name, str) for name in updated):
                        names = updated
                    elif isinstance(updated, dict) and type(updated.get('portrait_adjustment')) is bool:
                        portrait_adjustment = updated['portrait_adjustment']
            except (ValueError, TypeError):
                continue

    def current_names():
        with lock:
            return list(names)

    def current_portrait_adjustment():
        with lock:
            return portrait_adjustment

    threading.Thread(target=read_updates, daemon=True).start()
    try:
        watch_cameras(names, lambda value: send('message', value), lambda: False,
                      lambda value: send('invoked', value), lambda value: send('failed', value),
                      lambda value: send('progress', value), current_names,
                      lambda value: send('live_status', value), current_portrait_adjustment)
    except Exception as exc:
        send('error', str(exc) or type(exc).__name__)


if __name__ == '__main__':
    main()
