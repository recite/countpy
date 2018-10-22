# -*- coding: utf-8 -*-

"""
github.exceptions
~~~~~~~~~~~~~~~~~

This module contains the set of Github's exceptions.
"""
from requests import Response, codes
from json.decoder import JSONDecodeError

__all__ = [
    'GithubException',
    'DataDecodeError',
    'LoginError',
    'NotFoundError',
    'UserAgentError',
    'RateLimitError',
    'AbuseLimitError',
    'parse_response'
]


def parse_response(response):
    assert isinstance(response, Response), 'Invalid response object.'
    try:
        data = response.json()
    except JSONDecodeError:
        cls = DataDecodeError
        data = response.text
    else:
        if response.status_code is codes.OK:
            return data, response

        cls = GithubException
        message = data.get('message', '').lower()

        if response.status_code is codes.UNAUTHORIZED:
            cls = LoginError

        elif response.status_code is codes.FORBIDDEN:
            if 'invalid user-agent' in message:
                cls = UserAgentError
            elif 'rate limit exceeded' in message:
                cls = RateLimitError
            elif 'abuse' in message:
                cls = AbuseLimitError

        elif response.status_code is codes.NOT_FOUND:
            cls = NotFoundError

    raise cls(response.status_code, data)


class GithubException(Exception):
    def __init__(self, status, data):
        super(GithubException, self).__init__()
        self.status = status
        self.data = data

    def __str__(self):
        return '%s %s' % (self.status, self.data)


class DataDecodeError(Exception):
    pass


class LoginError(GithubException):
    pass


class NotFoundError(GithubException):
    pass


class UserAgentError(GithubException):
    pass


class RateLimitError(GithubException):
    pass


class AbuseLimitError(GithubException):
    pass
