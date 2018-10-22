# -*- coding: utf-8 -*-

import time
from requests.exceptions import Timeout, ConnectionError
from .exceptions import *
from . import RATE_LIMIT_URL

__all__ = ['GithubLimit', 'github_limit', 'reconnect']

MIN_REMAINING_OF_LIMIT = 1
MIN_DELAY_PER_REQUEST = 1
MORE_DELAY_IF_OUT_LIMIT = 1
SHORT_BREAK_DELAY = 1
MEDIUM_BREAK_DELAY = 3
LONG_BREAK_DELAY = 5
MAX_RETRIES_PER_REQUEST = 5


class GithubLimit:
    def __init__(self, endpoint):
        self.limit = 0
        self.remaining = 0
        self.reset = 0
        self._last_use = 0
        self._delay = None
        self._key = 'core'
        if endpoint and endpoint.startswith('search'):
            self._key = 'search'

    @property
    def now(self):
        return time.time()

    def has_data(self):
        return bool(self.reset) is True

    def _set_delay(self):
        assert self.has_data(), 'No limit data found.'
        delay = (self.reset - self.now) / self.limit
        if delay < MIN_DELAY_PER_REQUEST:
            self._delay = MIN_DELAY_PER_REQUEST
        else:
            self._delay = delay

    def ask(self, session, force=False):
        if force or self.stale():
            response = session.get(RATE_LIMIT_URL)
            data, _ = parse_response(response)
            self.update(data['resources'][self._key])
            self._set_delay()

    def update(self, data):
        for key, val in data.items():
            if hasattr(self, key):
                setattr(self, key, val)

    def stale(self):
        return self.reset <= self.now

    def in_limit(self):
        return self.remaining > MIN_REMAINING_OF_LIMIT

    def delay(self):
        # Calculate delay value
        delay = 0
        if self.in_limit():
            if self._last_use and self._delay:
                delay = self._last_use + self._delay - self.now
        else:
            delay = self.reset - self.now + MORE_DELAY_IF_OUT_LIMIT

        # Do delay
        if delay > 0:
            time.sleep(delay)

    def use(self):
        self.remaining -= 1
        self._last_use = self.now

    def __repr__(self):
        return str(self)

    def __str__(self):
        return '{}(limit={}, remaining={}, reset={})'.format(
            self.__class__.__name__, self.limit, self.remaining, self.reset)


def github_limit(request):
    def handler(client, *args, **kwargs):
        client.limit.ask(session=client.session)
        client.limit.delay()

        count = 0
        while count < MAX_RETRIES_PER_REQUEST:
            try:
                result = request(client, *args, **kwargs)
            except RateLimitError as exc:
                client.logger.error('GitHub limit exceeded: [%s]' % exc)
                client.limit.ask(session=client.session, force=True)
                client.delay(SHORT_BREAK_DELAY)
            except AbuseLimitError as exc:
                client.logger.error('GitHub abuse limit violated: [%s]' % exc)
                client.reset()
                client.delay(LONG_BREAK_DELAY)
            except GithubException as exc:
                client.logger.error('GitHub responds error: [%s]' % exc)
                if not isinstance(exc, (DataDecodeError, NotFoundError)):
                    raise
                client.delay(MEDIUM_BREAK_DELAY)
            except (Timeout, ConnectionError) as exc:
                client.logger.error(
                    'Request timeout or connection error: [%s]' % exc)
                client.reset()
                client.delay(LONG_BREAK_DELAY)
            else:
                client.limit.use()
                return result

            count += 1
            client.logger.info('Retrying the request...')

    return handler


def reconnect(request):
    def handler(*args, **kwargs):
        count = 0
        while count < MAX_RETRIES_PER_REQUEST:
            try:
                return request(*args, **kwargs)
            except AssertionError as exc:
                print('Request error: %s' % exc)
                time.sleep(LONG_BREAK_DELAY)
                count += 1
            except (Timeout, ConnectionError):
                time.sleep(MEDIUM_BREAK_DELAY)
                count += 1
    return handler
