# -*- coding: utf-8 -*-

"""
github.exceptions
~~~~~~~~~~~~~~~~~

This module contains the set of Github's exceptions.
"""
import time
from requests import Response, codes
from requests.exceptions import Timeout, ConnectionError
from json.decoder import JSONDecodeError
from modules.logger import get_logger

__all__ = [
    'GithubException',
    'LoginError',
    'NotFoundError',
    'BadRequestError',
    'RepoBlockedError',
    'ServiceUnavailableError',
    'UserAgentError',
    'RateLimitError',
    'AbuseLimitError',
    'BlobTooLargeError',
    'MaxRetriesExceeded',
    'LegalReasonError',
    'parse_response',
    'handle_exception'
]

SHORT_BREAK_DELAY = 5
MEDIUM_BREAK_DELAY = 15
LONG_BREAK_DELAY = 60
DEFAULT_BREAK_DELAY = MEDIUM_BREAK_DELAY


class GithubException(Exception):
    delay = None
    prefix = ''

    def __init__(self, status, data):
        super(GithubException, self).__init__()
        self.name = self.__class__.__name__
        self.status = status
        self.data = data
        self.message = ''
        if isinstance(data, dict) and 'message' in data:
            self.message = data['message']

    def __str__(self):
        return '%s: %s %s' % (
            self.prefix or self.name, self.status, self.message or self.data
        )


class NotFoundError(GithubException):
    pass


class BadRequestError(GithubException):
    pass


class RepoBlockedError(GithubException):
    pass


class ServiceUnavailableError(GithubException):
    delay = LONG_BREAK_DELAY


class LoginError(GithubException):
    pass


class UserAgentError(GithubException):
    pass


class RateLimitError(GithubException):
    delay = SHORT_BREAK_DELAY
    prefix = 'GitHub limit exceeded'


class AbuseLimitError(GithubException):
    delay = LONG_BREAK_DELAY
    prefix = 'GitHub abuse limit violated'


class BlobTooLargeError(GithubException):
    pass


class GithubServerError(GithubException):
    delay = LONG_BREAK_DELAY


class LegalReasonError(GithubException):
    pass


class MaxRetriesExceeded(Exception):
    pass


_logger = get_logger(__package__)
_need_reask = (RateLimitError,)
_need_reset = (Timeout, ConnectionError, AbuseLimitError)
_default_delay = (Timeout, ConnectionError)


def handle_exception(exception, delay_multiple=1, client=None):
    def delay(s):
        _logger.info('Resume in %s second%s...' % (s, 's' if s > 1 else ''))
        time.sleep(s * delay_multiple)

    _logger.error(exception)

    seconds = None
    if hasattr(exception, 'delay'):
        seconds = exception.delay
    elif isinstance(exception, _default_delay):
        seconds = DEFAULT_BREAK_DELAY

    if seconds is not None:
        delay(seconds)
        if client is not None:
            if isinstance(exception, _need_reask):
                client.ask_limit(force=True)
            elif isinstance(exception, _need_reset):
                client.reset()
        return

    raise exception


def parse_response(response, json=True):
    assert isinstance(response, Response), 'Invalid response object.'

    # Default exception
    cls = GithubException

    # Parse data in response
    try:
        data = response.json() if json else response.text
    except JSONDecodeError:
        data = response.text

    # Return parsed data and response object if success
    if response.status_code == codes.OK:
        return data, response

    # Parse GitHub error message
    try:
        message = data.get('message', '').lower()
    except AttributeError:
        message = data.lower()

    # Identify exception
    if response.status_code == codes.UNAUTHORIZED:
        cls = LoginError

    elif response.status_code == codes.FORBIDDEN:
        if 'invalid user-agent' in message:
            cls = UserAgentError
        elif 'rate limit exceeded' in message:
            cls = RateLimitError
        elif 'abuse' in message:
            cls = AbuseLimitError
        elif 'blob is too large' in message:
            cls = BlobTooLargeError
        elif 'repository access blocked' == message:
            cls = RepoBlockedError

    elif response.status_code == codes.NOT_FOUND:
        cls = NotFoundError

    elif response.status_code == codes.BAD_REQUEST:
        cls = BadRequestError

    elif response.status_code == codes.SERVICE_UNAVAILABLE:
        cls = ServiceUnavailableError

    elif response.status_code in (codes.SERVER_ERROR, codes.BAD_GATEWAY):
        cls = GithubServerError

    elif response.status_code == codes.UNAVAILABLE_FOR_LEGAL_REASONS:
        cls = LegalReasonError

    # Raise exception
    raise cls(response.status_code, data)
