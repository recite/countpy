# -*- coding: utf-8 -*-

import time
from types import SimpleNamespace
from requests import Session, Response, codes
from requests.exceptions import Timeout, ConnectionError
from json.decoder import JSONDecodeError
from urllib.parse import splitquery, parse_qsl
from . import _get_logger, get_endpoint, RATE_LIMIT_URL
from .exceptions import *

__all__ = ['GithubLimit', 'GithubClient', 'Pagination', 'Retriever']

REQUEST_TIMEOUT = 15
MIN_REMAINING_OF_LIMIT = 0
MIN_DELAY_PER_REQUEST = 1
MORE_DELAY_IF_OUT_LIMIT = .5
SHORT_BREAK_DELAY = 1
MEDIUM_BREAK_DELAY = 3
LONG_BREAK_DELAY = 5
MAX_RETRIES_PER_REQUEST = 5
MAX_RESULTS_PER_PAGE = 100


def retry(task):
    def waiter(client, *args, **kwargs):
        client.limit.ask(session=client.session)
        client.limit.delay()

        count = 0
        while count < MAX_RETRIES_PER_REQUEST:
            try:
                result = task(client, *args, **kwargs)
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

    return waiter


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


class GithubLimit:
    def __init__(self, endpoint):
        self.limit = 0
        self.remaining = 0
        self.reset = 0
        self._last_use = 0
        self._delay = None
        self._key = 'search' if endpoint.startswith('search') else 'core'

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


class GithubClient:
    def __init__(self, endpoint=None, auth=None, headers=None, timeout=None):
        self.method, self.url = get_endpoint(endpoint)
        self.default_headers = headers or {}
        self.timeout = timeout or REQUEST_TIMEOUT
        self.auth = auth
        self.limit = GithubLimit(endpoint)
        self.logger = _get_logger(self.__class__.__name__)
        self.initialize()

    def initialize(self):
        self.session = Session()
        if self.auth:
            self.session.auth = self.auth
        self.session.headers.update(self.default_headers)

    def reset(self):
        self.session.close()
        self.initialize()

    def delay(self, seconds):
        self.logger.info('Resume in %s second%s...'
                         % (seconds, 's' if seconds > 1 else ''))
        time.sleep(seconds)

    @retry
    def request(self, method=None, url=None, data=None, **kwargs):
        method = method or self.method
        url = url or self.url
        timeout = kwargs.pop('timeout', default=self.timeout)

        if 'data' in kwargs or 'json' in kwargs:
            raise NotImplementedError('Using "data" or "json" as argument is'
                                      'not allowed')

        response = self.session.request(
            method, url, timeout=timeout, json=data, **kwargs)

        return parse_response(response)


class Pagination(GithubClient):
    def __init__(self, per_page=None, *args, **kwargs):
        super(Pagination, self).__init__(*args, **kwargs)
        self.per_page = per_page or MAX_RESULTS_PER_PAGE
        self.incomplete = None
        self.total = None
        self.items = None
        self._links = None

    def __parse_links(self, response):
        links = {'cur': response.url}
        if 'Link' in response.headers:
            parse = lambda x, y: (y.split('=')[-1].strip(' "'), x.strip('< >'))
            links.update(dict(
                parse(*i.split(';'))
                for i in response.headers['Link'].split(',')))
        self._links = links

    def __parse_data(self, data):
        self.total = data['total_count']
        self.incomplete = data['incomplete_results']
        self.items = [SimpleNamespace(**item) for item in data['items']]

    def __prep_params(self, url, mapping):
        mapping.setdefault('params', {})
        mapping['params'].setdefault('per_page', self.per_page)
        # Params in URL will take precedence
        if url:
            qs = splitquery(url)[-1]
            if qs:
                for k, _ in parse_qsl(qs):
                    if k in mapping['params']:
                        del mapping['params'][k]

    def request(self, url=None, **kwargs):
        self.__prep_params(url, kwargs)
        data, resp = super(Pagination, self).request(url=url, **kwargs)
        self.__parse_data(data)
        self.__parse_links(resp)

    def has_next(self):
        return 'next' in self._links

    def has_data(self):
        return self.items is not None

    def next(self):
        assert self.has_next()
        self.request(url=self._links['next'])

    def iter(self):
        if self.has_data():
            while True:
                for i in self.items:
                    yield i
                if self.has_next():
                    self.next()
                    continue
                break


class Retriever(GithubClient):
    pass
