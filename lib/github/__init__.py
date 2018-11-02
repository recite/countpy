# -*- coding: utf-8 -*-

import os
from enum import Enum
from urllib.parse import urljoin

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_MAIN_DIR = os.path.dirname(_MODULE_DIR)

ROOT_ENDPOINT = 'https://api.github.com'
RATE_LIMIT_URL = urljoin(ROOT_ENDPOINT, 'rate_limit')


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
