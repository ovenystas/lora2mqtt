import sys
from unittest.mock import MagicMock

sys.modules['pyLoraRFM9x'] = MagicMock()
#sys.modules['paho'] = MagicMock()
