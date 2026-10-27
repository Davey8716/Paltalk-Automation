import unittest
from types import SimpleNamespace
from unittest.mock import patch

from paltalk_room_opener.automation import close_room


class CloseRoomTests(unittest.TestCase):
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

        button = Element(SimpleNamespace(AutomationId='Room close: The Garage', Name='', HelpText=''))
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
