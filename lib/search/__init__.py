# -*- coding: utf-8 -*-

import os
import logging
from configparser import ConfigParser

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Read config settings
config = ConfigParser(converters={'dict': lambda s: {
    k.strip(): v.strip()
    for k, v in (i.split(':') for i in s.split('\n'))
}})
config.read(os.path.join(_MODULE_DIR, 'settings.ini'))


def _get_logger(name):
    return logging.getLogger('%s.%s' % (__package__, name))


def _log_configurer():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt='%(message)s'))
    root = logging.getLogger(__package__)
    root.addHandler(handler)
    root.setLevel(logging.INFO)


from .run import SearchCode
