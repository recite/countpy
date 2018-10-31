# -*- coding: utf-8 -*-

import os
import logging
from logging.handlers import RotatingFileHandler
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


def _log_configurer(verbose=True, logfile=None):
    if verbose or logfile:
        formatter = logging.Formatter(fmt='%(message)s')
        root = logging.getLogger(__package__)
        root.setLevel(logging.INFO)
        if verbose:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            root.addHandler(stream_handler)
        if logfile:
            file_handler = RotatingFileHandler(
                logfile, maxBytes=20971520, backupCount=10)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)


from .run import SearchCode
