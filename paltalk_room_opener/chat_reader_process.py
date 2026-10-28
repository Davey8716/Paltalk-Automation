"""Isolated UI Automation scan, invoked by the chat reader worker."""

import json
import sys
from dataclasses import asdict

from .chat_reader import read_selected_room_chat


def main():
    try:
        result = {'snapshot': asdict(read_selected_room_chat())}
    except Exception as exc:
        result = {'error': str(exc).splitlines()[0].strip() or type(exc).__name__}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode('ascii'))
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
