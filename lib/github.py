# -*- coding: utf-8 -*-

import re
import os
import time
import datetime
import pickle

from copy import copy
from collections import deque
from threading import Thread, Lock
from github import Github, RateLimitExceededException

from app.models import Repository
from config import GITHUB_LOGINS, GITHUB_SEARCH_PERIOD, GITHUB_SEARCH_WINDOW, GITHUB_SEARCH_QUALIFIERS

MAX_RESULTS_PER_PAGE = 100  # the largest number of results per page is 100
MAX_TOTAL_RESULTS = 1000  # by default, GitHub APIv3 only returns 1000 results at maximum

_REPOSITORIES = dict()


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
    _save_as_file = os.path.join(os.path.dirname(__file__), '.timeslices')

    def __init__(self, period=GITHUB_SEARCH_PERIOD, window=GITHUB_SEARCH_WINDOW):
        self._lock = Lock()
        self._data = slice_period(period, window)
        self._total = len(self._data)
        self._count = self._total
        self._key = ''.join('{}{}'.format(period, window).split())
        self._done = self.__load()

    def __len__(self):
        return self._count

    def __load(self):
        if os.path.isfile(self._save_as_file):
            with open(self._save_as_file, 'rb') as fp:
                data = pickle.load(fp)
            if self._key in data:
                return data[self._key]
            else:
                os.remove(self._save_as_file)
        return set()

    def save(self):
        with open(self._save_as_file, 'wb') as fp:
            data = {self._key: self._done}
            pickle.dump(data, fp)

    def done(self, item):
        with self._lock:
            self._done.add(item)

    def get(self):
        with self._lock:
            while self._count > 0:
                item = self._data.popleft()
                self._count -= 1
                if item not in self._done:
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
        self._qualifiers = copy(GITHUB_SEARCH_QUALIFIERS).update(self._qualifiers)
        self.per_page = per_page

    def run(self):
        self._event.wait()
        while self._event.is_set():
            time_window = self._slices.get()
            if time_window is None:
                break
            self.__search(time_window)
            self._slices.done(time_window)

    def __limit_control(self, task):
        def waiter(*args, **kwargs):
            while True:
                try:
                    return task(*args, **kwargs)
                except RateLimitExceededException:
                    delay = self._conn.rate_limiting_resettime - time.time()
                    if delay > 0:
                        time.sleep(delay)
        return waiter

    @staticmethod
    def __find_total(query):
        total = query.totalCount
        if 0 < MAX_TOTAL_RESULTS < total:
            return MAX_TOTAL_RESULTS
        return total

    def __find_repos(self, query):
        total = self.__limit_control(self.__find_total)(query)
        if total > 0:
            for i in range(total):
                yield self.__limit_control(query.__getitem__)(i)

    def __find_files(self, repo):
        def retrieve(path):
            items = self.__limit_control(repo.get_contents)(path)
            for item in items:
                if item.download_url is not None:
                    yield item.path, self.__limit_control(item.decoded_content.decode)()
                else:
                    yield from retrieve(path=item.path)
        return retrieve(path='/')

    def __search(self, time_window):
        qualifiers = copy(self._qualifiers)
        qualifiers['created'] = time_window
        query = self._conn.search_repositories(self._keyword, **qualifiers)
        for repo in self.__find_repos(query):
            newrepo = Repository(repo.full_name)
            newrepo.set_id(repo.id)
            newrepo.set_url(repo.url)
            for path, content in self.__find_files(repo):
                newrepo.add_file(path, content)
            newrepo.find_packages()
            newrepo.commit_changes()


class SearchCode:
    def __init__(self):
        pass

