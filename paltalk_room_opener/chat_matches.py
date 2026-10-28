"""Identify new matching chat elements after establishing a room baseline."""

import unicodedata


def normalize_phrase(text):
    """Compare Unicode emoji regardless of their optional presentation selector."""
    return unicodedata.normalize('NFC', text).replace('\ufe0e', '').replace('\ufe0f', '').casefold()


class ChatMatchTracker:
    def __init__(self, phrases):
        self.phrases = tuple(phrase for phrase in phrases if phrase.strip())
        self.room_id = None
        self.seen = set()
        self.pending = set()

    def scan(self, snapshot):
        ids = set(snapshot.message_ids)
        if snapshot.room_id != self.room_id:
            self.room_id = snapshot.room_id
            self.seen = ids
            self.pending.clear()
            return []
        self.pending.update(ids - self.seen)
        self.pending.intersection_update(ids)
        self.seen.update(ids)
        matches = []
        for message in snapshot.messages:
            if message.runtime_id in self.pending:
                for phrase in self.phrases:
                    normalized = normalize_phrase(phrase)
                    if normalized and normalized in normalize_phrase(message.text):
                        matches.append((message, phrase))
                self.pending.discard(message.runtime_id)
        return matches
