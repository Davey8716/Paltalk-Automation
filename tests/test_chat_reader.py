import unittest

from paltalk_automation.admin_actions.backend.chat_reader import associate_messages


class ChatAssociationTests(unittest.TestCase):
    def test_grouped_messages_and_boundaries(self):
        rows = [
            ('message', (), 'unknown', (1,)), ('other', (), '', ()),
            ('message', ('Alice',), 'first', (2,)),
            ('message', (), 'second', (3,)),
            ('other', (), '', ()),
            ('message', (), 'unknown again', (4,)), ('other', (), '', ()),
            ('message', ('Bob',), 'hello', (5,)),
        ]
        self.assertEqual([(m.sender, m.text) for m in associate_messages(rows)],
                         [('Alice', 'first'), ('Alice', 'second'), ('Bob', 'hello')])

    def test_ambiguous_or_empty_sender_clears_group(self):
        rows = [('message', ('Alice',), 'first', (1,)), ('other', (), '', ()),
                ('message', ('Bob', 'Carol'), 'ambiguous', (2,)),
                ('message', (), 'unknown', (3,)),
                ('message', ('',), 'empty', (4,)),
                ('message', (), 'still unknown', (5,))]
        self.assertEqual([m.text for m in associate_messages(rows)], ['first'])

    def test_sender_at_end_of_group(self):
        rows = [('message', (), 'first', (1,)),
                ('message', ('Alice',), 'second', (2,)),
                ('other', (), '', ())]
        self.assertEqual([(m.sender, m.text) for m in associate_messages(rows)],
                         [('Alice', 'first'), ('Alice', 'second')])


if __name__ == '__main__':
    unittest.main()
