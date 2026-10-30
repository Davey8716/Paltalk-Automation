import unittest
import uuid

from paltalk_automation.single_instance import SingleInstance


class SingleInstanceTests(unittest.TestCase):
    def test_mutex_detects_an_existing_instance_and_is_released(self):
        name = 'Local\\PaltalkAutomationTest-' + str(uuid.uuid4())
        first = SingleInstance(name)
        second = None
        third = None
        try:
            self.assertFalse(first.already_running)
            second = SingleInstance(name)
            self.assertTrue(second.already_running)
            first.close()
            second.close()
            third = SingleInstance(name)
            self.assertFalse(third.already_running)
        finally:
            first.close()
            if second:
                second.close()
            if third:
                third.close()
