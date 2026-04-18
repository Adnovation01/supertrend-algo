import random
import string
import colorama
from .logger import logger_setup


# Terminal Colors
lg = colorama.Fore.LIGHTGREEN_EX
w  = colorama.Fore.WHITE
cy = colorama.Fore.CYAN
ye = colorama.Fore.YELLOW
r  = colorama.Fore.RED
n  = colorama.Fore.RESET
mg = colorama.Fore.MAGENTA
colors = [lg, r, w, cy, ye, mg]

VERSION_MAJOR = 2
VERSION_MINOR = 0
VERSION_FIX   = 0

VERSION = f'v{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_FIX}'


def handleYorN(input_string):
    yN = 0
    if input_string.lower() in ['y', 't', '1', 'yes', 'true']:
        yN = 1
    return yN


def generate_alphanumeric_secret(length=12):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def custom_round(value, base=.05, prec=2):
    return round(base * round(float(value) / base), prec)


class SharedResourceManager:
    def __init__(self):
        self.logger_global = logger_setup()
        self.public_url = ''


shared_obj = SharedResourceManager()
