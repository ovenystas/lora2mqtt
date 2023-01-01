import sys
import unittest
from unittest.mock import MagicMock, patch, call

import time

from log import Log

class TestLog(unittest.TestCase):

    @patch('sdnotify.SystemdNotifier')
    @patch('log.localtime')
    @patch('builtins.print')
    def test_print_nothing(self, mock_print, mock_localtime,  mock_sdnotify):
        mock_localtime.return_value = time.strptime(
            'sat may 15 12:11:30 2021')
        log = Log()
        log.print('Hello world', console=False)
        mock_print.assert_not_called()

    @patch('sdnotify.SystemdNotifier')
    @patch('log.localtime')
    @patch('builtins.print')
    def test_print_default(self, mock_print, mock_localtime,  mock_sdnotify):
        mock_localtime.return_value = time.strptime(
            'sat may 15 12:11:30 2021')
        log = Log()
        log.print('Hello world')
        mock_print.assert_called_with(
            '\x1b[32m[2021-05-15 12:11:30] \x1b[0mHello world\x1b[0m')

    @patch('sdnotify.SystemdNotifier')
    @patch('log.localtime')
    @patch('builtins.print')
    def test_print_warning(self, mock_print, mock_localtime,  mock_sdnotify):
        mock_localtime.return_value = time.strptime(
            'sat may 15 12:11:30 2021')
        log = Log()
        log.print('Hello world', warning=True)
        mock_print.assert_called_with(
            '\x1b[33m[2021-05-15 12:11:30] \x1b[0mHello world\x1b[0m')

    @patch('sdnotify.SystemdNotifier')
    @patch('log.localtime')
    @patch('builtins.print')
    def test_print_error(self, mock_print, mock_localtime,  mock_sdnotify):
        mock_localtime.return_value = time.strptime(
            'sat may 15 12:11:30 2021')
        log = Log()
        log.print('Hello world', error=True)
        mock_print.assert_called_with(
            '\x1b[31m\x1b[1m[2021-05-15 12:11:30] \x1b[0mHello world\x1b[0m',
            file=sys.stderr)

# TODO: Add sd_notify=True tests
 