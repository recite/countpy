# -*- coding: utf-8 -*-

import os
from configparser import ConfigParser

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Read config settings
config = ConfigParser(converters={'dict': lambda s: {
    k.strip(): v.strip()
    for k, v in (i.split(':') for i in s.split('\n'))
}})
config.read(os.path.join(_MODULE_DIR, 'settings.ini'))

# Initialize SearchCode
from .run import SearchCode
