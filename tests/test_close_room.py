import unittest
from types import SimpleNamespace
from unittest.mock import patch

from paltalk_room_opener.automation import close_room, room_states
from paltalk_room_opener.worker import CloseAllRoomsWorker


class CloseRoomTests(unittest.TestCase):
    def test_close_all_continues_after_a_room_fails(self):
        worker = CloseAllRoomsWorker(['Alpha', 'Beta'])
        messages = []
        worker.message.connect(messages.append)
        with patch('paltalk_room_opener.worker.close_room', side_effect=[RuntimeError('failure'), None]) as close:
            worker.run()
        self.assertEqual([call.args[0] for call in close.call_args_list], ['Alpha', 'Beta'])
        self.assertIn('Alpha', messages[0])

    def test_state_uses_identified_close_buttons_and_rejects_ambiguity(self):
        button = SimpleNamespace(Current=SimpleNamespace(AutomationId='Room close: The Garage'))
        with patch('paltalk_room_opener.automation.import_module', side_effect=[SimpleNamespace(AddReference=lambda _: None), object()]), \
             patch('paltalk_room_opener.automation._close_buttons', return_value=[button]):
            self.assertEqual(room_states(['The Garage', 'Other']), {'The Garage': True, 'Other': False})
        with patch('paltalk_room_opener.automation.import_module', side_effect=[SimpleNamespace(AddReference=lambda _: None), object()]), \
             patch('paltalk_room_opener.automation._close_buttons', return_value=[button, button]):
            self.assertEqual(room_states(['The Garage']), {})

    def test_matches_room_name_on_close_button_id(self):
        class Element:
            def __init__(self, current, children=()):
                self.Current = current
                self.children = children
                self.invoked = False

            def FindAll(self, *_args):
                return self.children

            def GetCurrentPattern(self, _pattern):
                return self

            def Invoke(self):
                self.invoked = True

        button = Element(SimpleNamespace(AutomationId='Room close: The Garage', Name='', HelpText='', IsEnabled=True))
        window = Element(SimpleNamespace(ProcessId=42), [button])
        root = Element(None, [window])
        element = SimpleNamespace(RootElement=root, ControlTypeProperty=1)
        automation = SimpleNamespace(AutomationElement=element, ControlType=SimpleNamespace(Window=1, Button=2),
                                     TreeScope=SimpleNamespace(Children=1, Descendants=2),
                                     PropertyCondition=lambda *args: args,
                                     InvokePattern=SimpleNamespace(Pattern=1))
        logs = []
        with patch('paltalk_room_opener.automation.import_module', side_effect=[SimpleNamespace(AddReference=lambda _: None), automation]), \
             patch('paltalk_room_opener.automation.psutil.process_iter', return_value=[SimpleNamespace(info={'pid': 42, 'name': 'Paltalk.exe'})]):
            close_room('The Garage', logs.append)
        self.assertTrue(button.invoked)
        self.assertIn('Invoked close', logs[0])


if __name__ == '__main__':
    unittest.main()
