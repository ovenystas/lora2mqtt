import sys
import sdnotify
from time import localtime, strftime
from colorama import Fore, Style
from unidecode import unidecode

class Log:

    def __init__(self):
        self.sd_notifier = sdnotify.SystemdNotifier()


    def print(self, text, error=False, warning=False, sd_notify=False, console=True):
        ''' 
        Logging function
        '''
        local_time = localtime()

        if console:
            timestamp = strftime('%Y-%m-%d %H:%M:%S', local_time)
            if error:
                print(f'{Fore.RED}{Style.BRIGHT}[{timestamp}] {Style.RESET_ALL}{text}{Style.RESET_ALL}', file=sys.stderr)
            elif warning:
                print(f'{Fore.YELLOW}[{timestamp}] {Style.RESET_ALL}{text}{Style.RESET_ALL}')
            else:
                print(f'{Fore.GREEN}[{timestamp}] {Style.RESET_ALL}{text}{Style.RESET_ALL}')

        if sd_notify:
            timestamp_sd = strftime('%b %d %H:%M:%S', local_time)
            self.sd_notifier.notify(f'STATUS={timestamp_sd} - {unidecode(text)}.')
