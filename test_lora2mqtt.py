import sys
import unittest
from unittest.mock import MagicMock, patch, call
import importlib

#import tests.mock_import
sys.modules['pyLoraRFM9x'] = MagicMock()
import lora2mqtt
#target = __import__("lora2mqtt/lora2mqtt.py")
#target = importlib.import_module('lora2mqtt', 'lora2mqtt')

class TestHappy(unittest.TestCase):

    @patch('builtins.print')
    def test_print_intro(self, mock_print):
        lora2mqtt.print_intro()
        mock_print.assert_has_calls([
            call('\x1b[32m\x1b[1m'),
            call(lora2mqtt.project_name),
            call('Source:', lora2mqtt.project_url),
            call('\x1b[0m')])

    @unittest.skip("Parse errors")
    def test_main(self):
        lora2mqtt.log = lora2mqtt.Log()
        lora2mqtt.main()

    def test_parse_arguments(self):
        parser = lora2mqtt.parse_arguments(['--config_dir', '.'])
        self.assertEqual(parser.config_dir, '.')

if __name__ == '__main__':
    unittest.main()
