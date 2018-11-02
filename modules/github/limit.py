# -*- coding: utf-8 -*-

import time
from . import RATE_LIMIT_URL
from .exceptions import parse_response, handle_exception, MaxRetriesExceeded

__all__ = ['GithubLimit', 'retry']

MIN_REMAINING_OF_LIMIT = 1
MIN_DELAY_PER_REQUEST = 1
MORE_DELAY_IF_OUT_LIMIT = 1
MAX_RETRIES_PER_REQUEST = 5


def retry(with_limit):
    def wrapper(request):
        def handler(*args, **kwargs):
            count = 1
            client = None

            if with_limit is True:
                client = args[0]
                client.ask_limit()
                client.delay_limit()

            while count <= MAX_RETRIES_PER_REQUEST:
                try:
                    result = request(*args, **kwargs)
                    if client is not None:
                        client.use_limit()
                    return result

                except Exception as exc:
                    handle_exception(exc, delay_multiple=count, client=client)
                    count += 1

            raise MaxRetriesExceeded('Unable to make request')
        return handler
    return wrapper


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

    @retry(with_limit=False)
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
