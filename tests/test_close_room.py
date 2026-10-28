import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from paltalk_room_opener.automation import (PaltalkWindowNotFound, _paltalk_main_window,
                                             _wait_for_paltalk_main_window, close_room, room_states, restore_paltalk)
from paltalk_room_opener.worker import CloseAllRoomsWorker


class CloseRoomTests(unittest.TestCase):
    def test_main_window_selection_ignores_other_processes_and_owned_dialogs(self):
        user32 = MagicMock()
        def enumerate_windows(callback, _):
            for hwnd in (101, 102, 103):
                callback(hwnd, 0)
            return True
        def get_pid(hwnd, target):
            target._obj.value = 42 if hwnd != 103 else 99
        def get_title(hwnd, buffer, size):
            buffer.value = 'Paltalk'
        def get_class(hwnd, buffer, size):
            buffer.value = 'Qt6111QWindowOwnDCIcon'
        user32.EnumWindows.side_effect = enumerate_windows
        user32.GetWindowThreadProcessId.side_effect = get_pid
        user32.GetWindow.side_effect = lambda hwnd, _: 101 if hwnd == 102 else 0
        user32.GetWindowLongW.return_value = 0x00010000
        user32.GetWindowTextLengthW.return_value = 7
        user32.GetWindowTextW.side_effect = get_title
        user32.GetClassNameW.side_effect = get_class
        with patch('paltalk_room_opener.automation.psutil.process_iter', return_value=[SimpleNamespace(info={'pid': 42, 'name': 'Paltalk.exe'})]):
            self.assertEqual(_paltalk_main_window(user32), 101)

    def test_main_window_selection_prefers_paltalk_main_qt_window(self):
        user32 = MagicMock()
        def enumerate_windows(callback, _):
            callback(101, 0)
            callback(102, 0)
            return True
        def get_pid(hwnd, target):
            target._obj.value = 42
        def get_title(hwnd, buffer, size):
            buffer.value = 'Paltalk'
        def get_class(hwnd, buffer, size):
            buffer.value = 'Qt6111QWindowOwnDCIcon' if hwnd == 101 else 'Qt6111QWindowIcon'
        user32.EnumWindows.side_effect = enumerate_windows
        user32.GetWindowThreadProcessId.side_effect = get_pid
        user32.GetWindow.return_value = 0
        user32.GetWindowLongW.return_value = 0x00010000
        user32.GetWindowTextLengthW.return_value = 7
        user32.GetWindowTextW.side_effect = get_title
        user32.GetClassNameW.side_effect = get_class
        with patch('paltalk_room_opener.automation.psutil.process_iter', return_value=[SimpleNamespace(info={'pid': 42, 'name': 'Paltalk.exe'})]):
            self.assertEqual(_paltalk_main_window(user32), 101)

    def test_main_window_unavailable_is_an_error(self):
        user32 = MagicMock()
        user32.EnumWindows.return_value = True
        with patch('paltalk_room_opener.automation.psutil.process_iter', return_value=[]), \
             self.assertRaisesRegex(RuntimeError, r'0 Paltalk process\(es\); top-level: 0, unowned: 0'):
            _paltalk_main_window(user32)

    def test_window_discovery_retries_until_window_appears(self):
        with patch('paltalk_room_opener.automation._paltalk_main_window',
                   side_effect=[PaltalkWindowNotFound('not ready'), 123]) as find, \
             patch('paltalk_room_opener.automation.time.monotonic', side_effect=[0, 0, 0]), \
             patch('paltalk_room_opener.automation.time.sleep'):
            self.assertEqual(_wait_for_paltalk_main_window(MagicMock()), 123)
        self.assertEqual(find.call_count, 2)

    def test_window_discovery_times_out_with_last_diagnostic(self):
        with patch('paltalk_room_opener.automation._paltalk_main_window',
                   side_effect=PaltalkWindowNotFound('2 eligible windows')), \
             patch('paltalk_room_opener.automation.time.monotonic', side_effect=[0, 4]), \
             self.assertRaisesRegex(PaltalkWindowNotFound, '2 eligible windows'):
            _wait_for_paltalk_main_window(MagicMock())

    def test_ambiguous_main_windows_are_rejected_with_counts(self):
        user32 = MagicMock()
        user32.EnumWindows.side_effect = lambda callback, _: (callback(101, 0), callback(102, 0), True)[-1]
        user32.GetWindowThreadProcessId.side_effect = lambda hwnd, target: setattr(target._obj, 'value', 42)
        user32.GetWindow.return_value = 0
        user32.GetWindowLongW.return_value = 0x00010000
        user32.GetWindowTextLengthW.return_value = 7
        user32.GetWindowTextW.side_effect = lambda hwnd, buffer, size: setattr(buffer, 'value', 'Paltalk')
        user32.GetClassNameW.side_effect = lambda hwnd, buffer, size: setattr(buffer, 'value', 'Qt6111QWindowOwnDCIcon')
        with patch('paltalk_room_opener.automation.psutil.process_iter', return_value=[SimpleNamespace(info={'pid': 42, 'name': 'Paltalk.exe'})]), \
             self.assertRaisesRegex(PaltalkWindowNotFound, r'title matches: 2, main-class matches: 2'):
            _paltalk_main_window(user32)

    def test_restore_requests_maximize_and_waits_until_ready(self):
        for initial_visible in (False, True):
            with self.subTest(initial_visible=initial_visible):
                user32 = MagicMock()
                user32.IsWindowVisible.side_effect = [initial_visible, True, True]
                user32.IsZoomed.side_effect = [False, False, True] if initial_visible else [False, True]
                with patch('paltalk_room_opener.automation.ctypes.WinDLL', return_value=user32), \
                     patch('paltalk_room_opener.automation._paltalk_main_window', return_value=123), \
                     patch('paltalk_room_opener.automation.time.sleep'):
                    restore_paltalk()
                user32.ShowWindowAsync.assert_called_once_with(123, 3)

    def test_already_maximized_window_needs_no_restore(self):
        user32 = MagicMock()
        with patch('paltalk_room_opener.automation.ctypes.WinDLL', return_value=user32), \
             patch('paltalk_room_opener.automation._paltalk_main_window', return_value=123):
            restore_paltalk()
        user32.ShowWindowAsync.assert_not_called()

    def test_restore_reselects_a_recreated_window(self):
        user32 = MagicMock()
        user32.IsWindow.side_effect = [True, True, False, True, True, True, True]
        user32.IsWindowVisible.return_value = False
        user32.IsWindowVisible.side_effect = [False, False, True]
        user32.IsZoomed.return_value = True
        with patch('paltalk_room_opener.automation.ctypes.WinDLL', return_value=user32), \
             patch('paltalk_room_opener.automation._paltalk_main_window', side_effect=[123, 456, 456]), \
             patch('paltalk_room_opener.automation.time.sleep'):
            restore_paltalk()
        self.assertEqual([call.args for call in user32.ShowWindowAsync.call_args_list], [(123, 3), (456, 3)])

    def test_restore_fails_when_request_fails_or_window_never_becomes_ready(self):
        for request_accepted in (False, True):
            with self.subTest(request_accepted=request_accepted):
                user32 = MagicMock()
                user32.IsWindowVisible.return_value = False
                user32.ShowWindowAsync.return_value = request_accepted
                with patch('paltalk_room_opener.automation.ctypes.WinDLL', return_value=user32), \
                     patch('paltalk_room_opener.automation._paltalk_main_window', return_value=123), \
                     patch('paltalk_room_opener.automation.time.monotonic', side_effect=[0, 0, 6]), \
                     self.assertRaises(RuntimeError):
                    restore_paltalk()

    def test_close_all_stops_if_restore_fails(self):
        worker = CloseAllRoomsWorker(['Alpha'])
        messages = []
        worker.message.connect(messages.append)
        with patch('paltalk_room_opener.worker.restore_paltalk', side_effect=RuntimeError('window unavailable')), \
             patch('paltalk_room_opener.worker.room_states') as states, \
             patch('paltalk_room_opener.worker.close_room') as close:
            worker.run()
        states.assert_not_called()
        close.assert_not_called()
        self.assertIn('window unavailable', messages[0])

    def test_close_all_continues_after_a_room_fails(self):
        worker = CloseAllRoomsWorker(['Alpha', 'Beta'])
        messages = []
        worker.message.connect(messages.append)
        with patch('paltalk_room_opener.worker.restore_paltalk') as restore, \
             patch('paltalk_room_opener.worker.room_states', return_value={'Alpha': True, 'Beta': True}), \
             patch('paltalk_room_opener.worker.close_room', side_effect=[RuntimeError('failure'), None]) as close:
            worker.run()
        restore.assert_called_once()
        self.assertEqual([call.args[0] for call in close.call_args_list], ['Alpha', 'Beta'])
        self.assertIn('Alpha', messages[0])

    def test_close_all_checks_state_after_restoring_and_skips_closed_rooms(self):
        worker = CloseAllRoomsWorker(['Alpha', 'Beta'])
        events = []
        with patch('paltalk_room_opener.worker.restore_paltalk', side_effect=lambda: events.append('restore')), \
             patch('paltalk_room_opener.worker.room_states', side_effect=lambda names: events.append('check') or {'Alpha': False, 'Beta': True}), \
             patch('paltalk_room_opener.worker.close_room', side_effect=lambda name, log: events.append(name)):
            worker.run()
        self.assertEqual(events, ['restore', 'check', 'Beta'])

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
