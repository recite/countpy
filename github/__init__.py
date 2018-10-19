# -*- coding: utf-8 -*-

import os
import logging
from enum import Enum
from configparser import ConfigParser
from urllib.parse import urljoin

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_MAIN_DIR = os.path.dirname(_MODULE_DIR)

ROOT_ENDPOINT = 'https://api.github.com'
RATE_LIMIT_URL = urljoin(ROOT_ENDPOINT, 'rate_limit')

# Read Github settings
config = ConfigParser(converters={'dict': lambda s: {
    k.strip(): v.strip()
    for k, v in (i.split(':') for i in s.split('\n'))
}})
config.read(os.path.join(_MODULE_DIR, 'settings.ini'))


class EndPoints(Enum):
    search_repositories = ('GET', '/search/repositories')


def get_endpoint(name):
    if name:
        try:
            method, path = EndPoints[name].value
            return method.upper(), urljoin(ROOT_ENDPOINT, path)
        except KeyError:
            pass
    return None, None


def _get_logger(name):
    return logging.getLogger('%s.%s' % (__package__, name))
