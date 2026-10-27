import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


class LauncherTests(unittest.TestCase):
    def test_missing_pythonnet_uses_project_environment(self):
        main = Path(__file__).resolve().parents[1] / 'main.py'
        with patch('importlib.util.find_spec', return_value=None), \
             patch('subprocess.Popen') as launch, \
             patch.object(Path, 'is_file', return_value=True), \
             patch('sys.prefix', str(main.parent / 'other-python')), \
             patch('sys.executable', 'pythonw.exe'):
            with self.assertRaises(SystemExit):
                runpy.run_path(str(main))
        self.assertEqual(Path(launch.call_args.args[0][0]).name, 'pythonw.exe')
        self.assertEqual(Path(launch.call_args.args[0][1]), main)


if __name__ == '__main__':
    unittest.main()
