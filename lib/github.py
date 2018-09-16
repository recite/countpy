# -*- coding: utf-8 -*-

import re
import time
import datetime
from copy import copy
from collections import deque, namedtuple
from threading import Thread, Lock
from github import Github, RateLimitExceededException
from github.PaginatedList import PaginatedList
from config import GITHUB_LOGINS, GITHUB_SEARCH_PERIOD, GITHUB_SEARCH_WINDOW, GITHUB_SEARCH_QUALIFIERS

MAX_RESULTS_PER_PAGE = 100
MAX_TOTAL_RESULTS = 1000

_REPOSITORIES = dict()

ContentFile = None


def to_second(time_annotation):
    matched = re.match(r'^\s*([1-9]+)?\s*(\w+)\s*$', time_annotation)
    if matched is not None:
        amount, time_unit = matched.groups()
        amount = int(amount) if amount else 1
        time_unit = time_unit.lower()

        factors = {
            1: ('s', 'sec', 'secs', 'second', 'seconds'),
            60: ('m', 'min', 'mins', 'minute', 'minutes'),
            3600: ('h', 'hr', 'hrs', 'hour', 'hours'),
            86400: ('d', 'day', 'days'),
            604800: ('w', 'week', 'weeks'),
            2592000: ('mo', 'month', 'months'),
            31536000: ('y', 'yr', 'year', 'years')
        }

        for factor, units in factors.items():
            if time_unit in units:
                return amount * factor

    raise ValueError('Unknown time annotation: "%s"' % time_annotation)


def slice_period(period, window):
    slices = deque()
    period = datetime.timedelta(seconds=to_second(period))
    window = datetime.timedelta(seconds=to_second(window))
    cur_date = datetime.datetime.utcnow().replace(microsecond=0, tzinfo=datetime.timezone.utc)
    cursor = cur_date - period
    while True:
        stop = cursor + window
        if stop >= cur_date:
            slices.append('>%s' % cursor.isoformat())
            break
        slices.append('%s..%s' % (cursor.isoformat(), stop.isoformat()))
        cursor = stop
    return slices


class TimeSlices:
    def __init__(self, period, window):
        self._data = slice_period(period, window)
        self._lock = Lock()
        self._total = len(self._data)
        self._count = self._total

    def get(self):
        with self._lock:
            if self._count > 0:
                item = self._data.popleft()
                self._count -= 1
                return item
            return None

    @property
    def status(self):
        with self._lock:
            return self._count, self._total


class SearchWorker(Thread):
    _keyword = ''  # empty means matching all
    _qualifiers = dict(
        language='python',
    )

    def __init__(self, user, passwd, slices, event, per_page=MAX_RESULTS_PER_PAGE):
        assert isinstance(slices, TimeSlices), 'An instance of %r is required.' % TimeSlices
        assert per_page > 0, 'Number of items per page must be greater than zero.'
        super(SearchWorker, self).__init__()
        self._conn = Github(user, passwd, per_page=per_page)
        self._slices = slices
        self._event = event
        self.per_page = per_page

    def run(self):
        self._event.wait()
        while True:
            if not self._event.is_set():
                break
            time_window = self._slices.get()
            if time_window is None:
                break
            self.__search(time_window)

    def __wait(self):
        delay = self._conn.rate_limiting_resettime - time.time()
        if delay > 0:
            time.sleep(delay)

    def __find_total(self, query):
        assert isinstance(query, PaginatedList)
        while True:
            try:
                total = query.totalCount
            except RateLimitExceededException:
                self.__wait()
            else:
                if 0 < MAX_TOTAL_RESULTS < total:
                    return MAX_TOTAL_RESULTS
                return total

    def __find_items(self, query):
        assert isinstance(query, PaginatedList)
        total = self.__find_total(query)
        if total > 0:
            for i in range(total):
                while True:
                    try:
                        yield query[i]
                        break
                    except RateLimitExceededException:
                        self.__wait()

    def __search(self, time_window):
        qualifiers = copy(self._qualifiers)
        qualifiers.update(GITHUB_SEARCH_QUALIFIERS)
        qualifiers['created'] = time_window
        query = self._conn.search_repositories(self._keyword, **qualifiers)
        for repo in self.__find_items(query):
            if repo.full_name not in _REPOSITORIES:
                _REPOSITORIES[repo.full_name] = self.__crawl(repo)

    def __crawl(self, repo):
        return []


class SearchCode:
    def __init__(self):
        pass

