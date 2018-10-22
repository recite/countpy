# -*- coding: utf-8 -*-

"""
github.exceptions
~~~~~~~~~~~~~~~~~

This module contains the set of Github's exceptions.
"""

__all__ = [
    'GithubException',
    'DataDecodeError',
    'LoginError',
    'NotFoundError',
    'UserAgentError',
    'RateLimitError',
    'AbuseLimitError'
]


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
