import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from paltalk_room_opener.automation import _navigate_my_rooms


class MyRoomsNavigationTests(unittest.TestCase):
    def setUp(self):
        self.api = SimpleNamespace(
            AndCondition=lambda *args: args,
            PropertyCondition=lambda prop, value: (prop, value),
            AutomationElement=SimpleNamespace(NameProperty='name', ControlTypeProperty='type'),
            ControlType=SimpleNamespace(Button='button', CheckBox='checkbox'),
            TreeScope=SimpleNamespace(Descendants='descendants'),
            InvokePattern=SimpleNamespace(Pattern='invoke'),
            TogglePattern=SimpleNamespace(Pattern='toggle'),
            ToggleState=SimpleNamespace(On='on'))
        self.browse = MagicMock()
        self.rooms = MagicMock()
        self.tab = MagicMock()
        self.browse.Current.IsEnabled = self.rooms.Current.IsEnabled = self.tab.Current.IsEnabled = True
        self.browse.Current.IsOffscreen = self.rooms.Current.IsOffscreen = self.tab.Current.IsOffscreen = False
        self.toggle = SimpleNamespace(Current=SimpleNamespace(ToggleState='on'))
        self.browse_invoke = MagicMock()
        self.rooms_invoke = MagicMock()
        self.tab_invoke = MagicMock()
        self.tab_invoke.Invoke.side_effect = lambda: setattr(self.toggle.Current, 'ToggleState', 'on')
        self.browse.GetCurrentPattern.return_value = self.browse_invoke
        self.rooms.GetCurrentPattern.return_value = self.rooms_invoke
        self.tab.GetCurrentPattern.side_effect = lambda pattern: self.toggle if pattern == 'toggle' else self.tab_invoke
        self.window = MagicMock()
        self.controls = {'Browse Chat Rooms': [self.browse], 'ContactList_RoomsButton': [self.rooms],
                         'My Rooms': [self.tab]}
        self.window.FindAll.side_effect = lambda scope, condition: self.controls.get(condition[0][1], [])

    def test_selected_tab_is_not_toggled(self):
        with patch('paltalk_room_opener.automation._paltalk_windows', return_value=[self.window]):
            _navigate_my_rooms(self.api)
        self.browse_invoke.Invoke.assert_called_once()
        self.rooms_invoke.Invoke.assert_not_called()
        self.tab_invoke.Invoke.assert_not_called()

    def test_open_room_view_uses_rooms_navigation(self):
        self.controls['Browse Chat Rooms'] = []
        self.toggle.Current.ToggleState = 'off'
        with patch('paltalk_room_opener.automation._paltalk_windows', return_value=[self.window]):
            _navigate_my_rooms(self.api)
        self.rooms_invoke.Invoke.assert_called_once()
        self.browse_invoke.Invoke.assert_not_called()
        self.tab_invoke.Invoke.assert_called_once()

    def test_other_tab_is_selected(self):
        self.toggle.Current.ToggleState = 'off'
        with patch('paltalk_room_opener.automation._paltalk_windows', return_value=[self.window]):
            _navigate_my_rooms(self.api)
        self.tab_invoke.Invoke.assert_called_once()
        self.assertEqual(self.toggle.Current.ToggleState, 'on')

    def test_missing_control_and_stop_are_reported(self):
        with patch('paltalk_room_opener.automation._paltalk_windows', return_value=[]), \
             patch('paltalk_room_opener.automation.time.monotonic', side_effect=[0, 6]):
            with self.assertRaisesRegex(RuntimeError, 'room navigation button'):
                _navigate_my_rooms(self.api)
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            _navigate_my_rooms(self.api, stopped=lambda: True)


if __name__ == '__main__':
    unittest.main()
