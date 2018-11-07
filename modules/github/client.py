# -*- coding: utf-8 -*-

import re
from collections import deque
from operator import itemgetter
from types import SimpleNamespace
from requests import Session
from base64 import b64decode
from urllib.parse import splitquery, parse_qsl, urljoin, quote
from modules.logger import get_logger
from . import get_endpoint
from .limit import GithubLimit, retry
from .exceptions import parse_response, NotFoundError, \
    BadRequestError, BlobTooLargeError, GithubException

__all__ = [
    'GithubClient',
    'Pagination',
    'ContentRetriever',
    'GithubContent',
    'GithubSearch'
]

DEFAULT_REQUEST_TIMEOUT = 15
MAX_RESULTS_PER_PAGE = 100


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
        self.logger = get_logger(__package__)
        self.__create()

    def __create(self):
        self.session = Session()
        if self.auth:
            self.session.auth = self.auth
        self.session.headers.update(self.default_headers)

    def reset(self):
        self.session.close()
        self.__create()
        self.ask_limit(force=True)

    def ask_limit(self, force=False):
        self.limit.ask(self.session, force=force)

    def use_limit(self):
        self.limit.use()

    def delay_limit(self):
        self.limit.delay()

    @retry(with_limit=True)
    def request(self, method=None, url=None, data=None, **kwargs):
        method = method or self.method
        url = url or self.url
        timeout = kwargs.pop('timeout', self.timeout)

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
        try:
            data, resp = super(Pagination, self).request(url=url, **kwargs)
        except (NotFoundError, BadRequestError):
            pass
        else:
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
        query = ' '.join(
            [keyword] + ['{}:{}'.format(k, v) for k, v in qualifiers.items()]
        ).strip()

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

    @property
    def decoded_content(self):
        assert self.is_file(), 'Not a file'
        if hasattr(self, 'content'):
            if hasattr(self, 'encoding'):
                if self.encoding == 'base64':
                    try:
                        return b64decode(self.content).decode()
                    except UnicodeDecodeError:
                        return ''
                raise NotImplementedError(self.encoding)
            return self.content or ''
        return ''


class ContentRetriever(GithubClient):
    _excludes = re.compile(
        r'(?:^|/)'
        r'(\w*venv|site-packages|__pycache__|static|\.\w+'
        r'|[Pp](?:ython|ip)(?:-?\d+(?:\.[0-9a-z]+)*)?)'
        r'(?=/|$)'
    )

    @classmethod
    def is_excluded(cls, path):
        found = cls._excludes.findall(path)
        return bool(found)

    def __init__(self, auth=None, timeout=None):
        super(ContentRetriever, self).__init__(auth=auth, timeout=timeout)
        self.method = 'GET'

    def __retrieve(self, url, output='many'):
        try:
            data, _ = self.request(url=url)
        except (NotFoundError, BadRequestError):
            data = []

        islist = isinstance(data, list)
        if output == 'many':
            return data if islist else [data]
        elif output == 'one':
            return itemgetter(0)(data or [None]) if islist else data

        raise NotImplementedError(output)

    def retrieve(self, url):
        yield from (GithubContent(**i) for i in self.__retrieve(url))

    def retrieve_content(self, item):
        assert isinstance(item, GithubContent), 'Requires <GithubContent> item'
        if item.is_file():
            try:
                data = self.__retrieve(item.url, output='one')  # type: dict
            except BlobTooLargeError:
                try:
                    data = self.__retrieve(item.download_url, output='one')  # type: str
                except GithubException:
                    return
                else:
                    setattr(item, 'content', data)
            else:
                for attr in ('content', 'encoding'):
                    setattr(item, attr, data[attr])

    def traverse(self, contents_url):
        traversed = set()
        folders = deque(['.'])
        while True:
            try:
                folder = folders.popleft()
            except IndexError:
                break
            else:
                traversed.add(folder)
                for item in self.retrieve(urljoin(contents_url, folder)):
                    if item.is_file():
                        yield item
                    elif self.is_excluded(item.path):
                        continue
                    else:
                        path = quote(item.path)
                        if path not in traversed:
                            folders.append(path)
