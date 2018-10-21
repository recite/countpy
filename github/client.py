# -*- coding: utf-8 -*-

import time
from collections import deque
from types import SimpleNamespace
from requests import Session, Response, codes
from urllib.parse import splitquery, parse_qsl, urljoin
from json.decoder import JSONDecodeError
from . import _get_logger, get_endpoint
from .limit import GithubLimit, github_limit, reconnect
from .exceptions import *

__all__ = [
    'GithubClient',
    'Pagination',
    'ContentRetriever',
    'GithubContent',
    'GithubSearch'
]

DEFAULT_REQUEST_TIMEOUT = 15
MAX_RESULTS_PER_PAGE = 100


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


class GithubClient:
    default_headers = {
        'Accept': 'application/vnd.github.v3+json'
    }

    def __init__(self, endpoint=None, auth=None, headers=None, timeout=None):
        self._endpoint = endpoint
        self.method, self.url = get_endpoint(endpoint)
        if headers:
            self.default_headers.update(headers)
        self.timeout = timeout or DEFAULT_REQUEST_TIMEOUT
        self.auth = auth
        self.limit = GithubLimit(endpoint)
        self.logger = _get_logger(self.__class__.__name__)
        self.__create()

    def __create(self):
        self.session = Session()
        if self.auth:
            self.session.auth = self.auth
        self.session.headers.update(self.default_headers)

    def reset(self):
        self.session.close()
        self.__create()

    def delay(self, seconds):
        self.logger.info('Resume in %s second%s...'
                         % (seconds, 's' if seconds > 1 else ''))
        time.sleep(seconds)

    @github_limit
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
    def __init__(self, per_page=None, parser=None, **kwargs):
        super(Pagination, self).__init__(**kwargs)
        self.per_page = per_page
        if per_page and per_page > MAX_RESULTS_PER_PAGE:
            self.per_page = MAX_RESULTS_PER_PAGE
        self.items = None
        self._links = None
        self._parser = parser or SimpleNamespace

    def _parse_links(self, response):
        links = {'cur': response.url}
        if 'Link' in response.headers:
            parse = lambda x, y: (y.split('=')[-1].strip(' "'), x.strip('< >'))
            links.update(dict(
                parse(*i.split(';'))
                for i in response.headers['Link'].split(',')))
        self._links = links

    def _parse_data(self, data):
        if not isinstance(data, list):
            data = [data]
        self.items = [self._parser(**item) for item in data]

    def _prep_params(self, url, mapping):
        mapping.setdefault('params', {})
        if self.per_page is not None:
            mapping['params'].setdefault('per_page', self.per_page)
        # Params in URL will take precedence
        if url:
            qs = splitquery(url)[-1]
            if qs:
                for k, _ in parse_qsl(qs):
                    if k in mapping['params']:
                        del mapping['params'][k]

    def request(self, url=None, **kwargs):
        self._prep_params(url, kwargs)
        data, resp = super(Pagination, self).request(url=url, **kwargs)
        self._parse_links(resp)
        self._parse_data(data)

    def has_next(self):
        return 'next' in self._links

    def has_data(self):
        return self.items is not None

    def next(self):
        assert self.has_next()
        self.request(url=self._links['next'])

    def traverse(self):
        if self.has_data():
            while True:
                for i in self.items:
                    yield i
                if self.has_next():
                    self.next()
                    continue
                break


class GithubSearch(Pagination):
    def __init__(self, keyword=None,
                 qualifiers=None, sort=None, order=None, **kwargs):
        super(GithubSearch, self).__init__(**kwargs)
        assert self._endpoint and self._endpoint.startswith('search')
        self._keyword = keyword or ''
        self._qualifiers = qualifiers or {}
        self._sort, self._order = sort, order
        self.incomplete = None
        self.total = None

    def _parse_data(self, data):
        self.total = data['total_count']
        self.incomplete = data['incomplete_results']
        super(GithubSearch, self)._parse_data(data=data['items'])

    def search(self, keyword=None, sort=None, order=None, **qualifiers):
        sort = sort or self._sort
        order = order or self._order
        keyword = keyword or self._keyword

        # Construct qualifiers for search query
        qualifiers.update(
            {k: v for k, v in self._qualifiers.items() if k not in qualifiers})
        query = '+'.join(
            [keyword] + ['{}:{}'.format(k, v) for k, v in qualifiers.items()]
        ).strip(' +')

        # Construct search params
        assert query, '"q" param must not be empty.'
        params = {'q': query}
        if sort:
            params['sort'] = sort
        if order:
            params['order'] = order

        # Make request
        self.request(params=params)


class GithubContent(SimpleNamespace):
    def is_file(self):
        return self.type == 'file'

    @reconnect
    def __download(self):
        if self.download_url is not None:
            with Session() as s:
                resp = s.get(self.download_url)
            assert resp.status_code is codes.OK, '{} {}'.format(
                resp.status_code, resp.text)
            return resp.text

    @property
    def content(self):
        assert self.is_file(), 'Not a file.'
        if not hasattr(self, '_content'):
            self._content = self.__download()
        return self._content


class ContentRetriever(GithubClient):
    def __init__(self, contents_url, auth=None, timeout=None):
        super(ContentRetriever, self).__init__(auth=auth, timeout=timeout)
        self.method, self.url = 'GET', contents_url

    def retrieve(self, path='.'):
        data, _ = self.request(url=urljoin(self.url, path))
        if not isinstance(data, list):
            data = [data]
        yield from (GithubContent(**i) for i in data)

    def traverse(self):
        folders = deque(['.'])
        while True:
            try:
                folder = folders.popleft()
            except IndexError:
                break
            else:
                for item in self.retrieve(folder):
                    if item.is_file():
                        yield item
                    else:
                        folders.append(item.path)
