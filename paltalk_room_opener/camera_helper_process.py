"""Run camera monitoring outside the user-interface process."""

import json
import sys

from .camera_automation import watch_cameras


def send(kind, value):
    sys.stdout.write(json.dumps({'kind': kind, 'value': value}, ensure_ascii=True) + '\n')
    sys.stdout.flush()


def main():
    names = json.loads(sys.argv[1])
    try:
        watch_cameras(names, lambda value: send('message', value), lambda: False,
                      lambda value: send('invoked', value), lambda value: send('failed', value),
                      lambda value: send('progress', value))
    except Exception as exc:
        send('error', str(exc) or type(exc).__name__)


if __name__ == '__main__':
    main()
