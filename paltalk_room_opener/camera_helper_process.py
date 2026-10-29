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
    manual_prompt = json.loads(sys.argv[3]) if len(sys.argv) > 3 else False
    manual_generation = 0
    lock = threading.Lock()

    def read_updates():
        nonlocal names, portrait_adjustment, manual_prompt, manual_generation
        for line in sys.stdin:
            try:
                updated = json.loads(line)
                with lock:
                    if isinstance(updated, list) and all(isinstance(name, str) for name in updated):
                        names = updated
                    elif isinstance(updated, dict) and type(updated.get('manual_prompt')) is bool:
                        manual_prompt = updated['manual_prompt']
                        manual_generation += 1
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

    def current_manual_prompt():
        with lock:
            return manual_prompt, manual_generation

    threading.Thread(target=read_updates, daemon=True).start()
    try:
        watch_cameras(names, lambda value: send('message', value), lambda: False,
                      lambda value: send('invoked', value), lambda value: send('failed', value),
                      lambda value: send('progress', value), current_names,
                      lambda value: send('live_status', value), current_portrait_adjustment,
                      current_manual_prompt, lambda value: send('manual_opened', value))
    except Exception as exc:
        send('error', str(exc) or type(exc).__name__)


if __name__ == '__main__':
    main()
