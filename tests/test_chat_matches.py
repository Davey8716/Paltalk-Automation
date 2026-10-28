import unittest

from paltalk_room_opener.chat_matches import ChatMatchTracker
from paltalk_room_opener.chat_reader import ChatMessage, ChatSnapshot


def snapshot(room, messages, extra_ids=()):
    return ChatSnapshot((room,), tuple(messages), tuple(m.runtime_id for m in messages) + extra_ids)


class ChatMatchTests(unittest.TestCase):
    def test_emoji_presentation_variants_match(self):
        tracker = ChatMatchTracker(['Hey ❤️'])
        tracker.scan(snapshot(1, []))
        message = ChatMessage('Alice', 'hey ❤', (1,))
        self.assertEqual(tracker.scan(snapshot(1, [message])), [(message, 'Hey ❤️')])

    def test_baseline_repeated_scans_and_identical_posts(self):
        tracker = ChatMatchTracker(['Hey 👏'])
        old = ChatMessage('Alice', 'HEY 👏', (1,))
        new = ChatMessage('Alice', 'HEY 👏', (2,))
        self.assertEqual(tracker.scan(snapshot(1, [old])), [])
        self.assertEqual(tracker.scan(snapshot(1, [old, new])), [(new, 'Hey 👏')])
        self.assertEqual(tracker.scan(snapshot(1, [old, new])), [])

    def test_room_change_rebaselines_and_unknown_sender_is_seen(self):
        tracker = ChatMatchTracker(['spam'])
        self.assertEqual(tracker.scan(snapshot(1, [], ((10,),))), [])
        late = ChatMessage('Bob', 'spam', (10,))
        self.assertEqual(tracker.scan(snapshot(1, [late])), [])
        self.assertEqual(tracker.scan(snapshot(2, [late])), [])
        self.assertEqual(tracker.scan(snapshot(1, [late])), [])

    def test_new_message_waits_for_sender(self):
        tracker = ChatMatchTracker(['spam'])
        tracker.scan(snapshot(1, []))
        self.assertEqual(tracker.scan(snapshot(1, [], ((10,),))), [])
        message = ChatMessage('Bob', 'spam', (10,))
        self.assertEqual(tracker.scan(snapshot(1, [message])), [(message, 'spam')])
        self.assertEqual(tracker.scan(snapshot(1, [message])), [])


if __name__ == '__main__':
    unittest.main()
