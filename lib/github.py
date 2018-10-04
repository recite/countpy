# -*- coding: utf-8 -*-

import re
import os
import time
import datetime
import pickle
import logging

from copy import copy
from random import randint
from collections import deque, Iterable
from threading import Thread, Lock, Event
from configparser import ConfigParser
from github import Github, RateLimitExceededException, GithubException

from . import _MODULE_DIR
from app.models import Repository

__all__ = ['SearchCode', 'TimeSlices', 'SearchWorker']

# Default constants
MAX_RESULTS_PER_PAGE = 100  # the largest number of results per page is 100
MAX_TOTAL_RESULTS = 1000  # by default, GitHub APIv3 only returns 1000 results at maximum

# Delay controls
EXCEPTION_DELAY = 180  # 3 minutes
REQUEST_DELAY_MIN = 1
REQUEST_DELAY_MAX = 1
REQUEST_DELAY_MAX_DECIMALS = 999999

# Method for matching a string if it is time_annotation
match_time_annotation = re.compile(r'^\s*([1-9]+)?\s*(\w+)\s*$').match

# Read Github settings
config = ConfigParser(
    converters={'dict': lambda s: {k.strip(): v.strip() for k, v in (i.split(':') for i in s.split('\n'))}})
config.read(os.path.join(_MODULE_DIR, 'github.ini'))


def _log_configurer():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt='%(message)s'))
    root = logging.getLogger(__package__)
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _randf(minint, maxint, maxdec):
    base = randint(minint, maxint)
    return float('{}{}'.format(
        str(float(base)).rstrip('0'),
        '%0{}d'.format(len(str(maxdec))) % randint(0, int(maxdec))
    )) if int(maxdec) > 0 else float(base)


def _to_second(time_annotation):
    """
    Convert time_annotation string into number of seconds.

    :param str time_annotation: a time annotation string to convert
    :return: total number of seconds
    :rtype: int
    :raises ValueError: if time annotation is unknown
    """

    matched = match_time_annotation(time_annotation)
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


def _slice_period(period, window, reverse=True):
    """
    Slices time period into time windows. Format each time window (a slice) by
    following the time pattern of Github search API.

    :param str period: a time period to be sliced (time_annotation format)
    :param str window: a time window for slicing (time_annotation format)
    :param bool reverse: reverse order of result list returned
    :return: list of formatted time windows
    :rtype: deque[str]
    """

    period = datetime.timedelta(seconds=_to_second(period))
    window = datetime.timedelta(seconds=_to_second(window))
    cur_date = datetime.datetime.utcnow().replace(microsecond=0, tzinfo=datetime.timezone.utc)
    cursor = cur_date - period

    slices = []
    while True:
        stop = cursor + window
        if stop >= cur_date:
            slices.append('>%s' % cursor.isoformat())
            break
        slices.append('%s..%s' % (cursor.isoformat(), stop.isoformat()))
        cursor = stop

    return deque(reversed(slices) if reverse else slices)


def _minzero(number):
    return 0 if number < 0 else number


class ProgressBar:
    __end_char = '\n'
    __empty_char = '-'
    __filled_char = '█'

    __print_fmt = '\r{prefix} |{bar}| {rate}% {suffix}'

    def __init__(self, total, prefix='Progress:', suffix='Complete', decimals=1, length=50):
        self.total = int(total)
        self.length = int(length)
        self.params = {'prefix': prefix, 'suffix': suffix}
        self.__rate_fmt = '{0:.%sf}' % decimals
        self.__printed = False
        self.__last_printed = False

    def __print_bar(self, end=None, **params):
        end = end or '\r'
        print(self.__print_fmt.format(**params), end=end)
        if not self.__printed:
            self.__printed = True
        if end == self.__end_char:
            self.__last_printed = True

    def __gen_params(self, complete):
        filled_length = int(self.length * complete // self.total)
        filled_chars = self.__filled_char * filled_length

        empty_length = self.length - filled_length
        empty_chars = self.__empty_char * empty_length

        rate = self.__rate_fmt.format(complete / float(self.total) * 100)
        bar = '{}{}'.format(filled_chars, empty_chars)
        return dict(bar=bar, rate=rate, **self.params)

    def print(self, complete=0):
        end = self.__end_char if complete == self.total else None
        params = self.__gen_params(complete)
        self.__print_bar(end, **params)

    def end(self):
        if self.__printed and not self.__last_printed:
            print()


class TimeSlices:
    _save_as_file = os.path.join(_MODULE_DIR, '.timeslices')

    def __init__(self, period=None, window=None, reverse=None, resume=True):
        period = period or config.get('search_options', 'period')
        window = window or config.get('search_options', 'window')
        reverse = reverse if reverse is not None else config.getboolean('search_options', 'newest_first')

        self._resume = resume
        self._datakey = '_'.join('{}:{}'.format(period, window).split())
        self._data = _slice_period(period, window, reverse)
        self._total = len(self._data)
        self._count = self._total

        self._lock = Lock()
        self._completed = self._total == 0
        self._tasks_done = self.__load()

    def __len__(self):
        with self._lock:
            return self._count

    def __load(self):
        if self._resume:
            if os.path.isfile(self._save_as_file):
                with open(self._save_as_file, 'rb') as fp:
                    data = pickle.load(fp)
                if self._datakey in data:
                    return data[self._datakey]
                else:
                    os.remove(self._save_as_file)
            return set()

        # No resume
        if os.path.isfile(self._save_as_file):
            os.remove(self._save_as_file)
        return None

    def has_changes(self):
        with self._lock:
            return self._count != self._total

    def save(self):
        if self._resume:
            with self._lock:
                data = {self._datakey: self._tasks_done}
            with open(self._save_as_file, 'wb') as fp:
                pickle.dump(data, fp)

    def done(self, item):
        if self._resume:
            with self._lock:
                self._tasks_done.add(item)

    def get(self):
        with self._lock:
            while self._count > 0:
                item = self._data.popleft()
                self._count -= 1
                # No resume
                if not self._resume:
                    return item
                # Has resume
                if item not in self._tasks_done:
                    return item
        self._completed = True
        return None

    def is_completed(self):
        return self._completed

    def status(self):
        with self._lock:
            return self._count, self._total

    @property
    def remain(self):
        with self._lock:
            return self._total - self._count


class SearchWorker(Thread):
    _keyword = ''  # empty means matching all

    _qualifiers = config.getdict('search_options', 'qualifiers', fallback={})
    _qualifiers['language'] = 'python'

    def __init__(self, user, passwd, slices, event, per_page=MAX_RESULTS_PER_PAGE):
        assert isinstance(slices, TimeSlices), 'An instance of %r is required.' % TimeSlices
        assert per_page > 0, 'Number of items per page must be greater than zero.'
        super(SearchWorker, self).__init__()
        self._conn = Github(user, passwd, per_page=per_page)
        self._user = user
        self._slices = slices
        self._event = event
        self.per_page = per_page
        self._exception = None
        self._last_request = None
        self._logger = logging.getLogger('%s.%s' % (__package__, self.__class__.__name__))

    def get_exception(self):
        return self._exception

    def is_running(self):
        return self._event.is_set()

    def run(self):
        self._event.wait()
        self._logger.info('Search worker (%s) is started' % self._user)
        try:
            while self._event.is_set():
                time_window = self._slices.get()
                if time_window is not None:
                    try:
                        self.__search(time_window)
                        self._slices.done(time_window)
                        continue
                    except AssertionError:
                        pass
                break
        except Exception as exc:
            self._exception = exc

        self._logger.info('Search worker (%s) is stopped.' % self._user)

    def __limit_control(self, task):
        def waiter(*args, **kwargs):
            try:
                seconds = _randf(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, REQUEST_DELAY_MAX_DECIMALS)
                time.sleep(self._last_request + seconds - time.time())
            except (TypeError, ValueError):
                pass

            while True:
                try:
                    result = task(*args, **kwargs)
                except RateLimitExceededException as exc:
                    delay = _minzero(self._conn.rate_limiting_resettime - time.time())
                    self._logger.info('GitHub limit reached: [%s], resume in %s seconds...' % (exc, delay))
                    time.sleep(delay)
                except GithubException as exc:
                    self._logger.info('GitHub server responses: [%s], '
                                      'resume in %s seconds...' % (exc, EXCEPTION_DELAY))
                    time.sleep(EXCEPTION_DELAY)
                else:
                    self._last_request = time.time()
                    return result

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
            self._logger.info('* %d repositories found' % total)
            for i in range(total):
                assert self.is_running()
                try:
                    yield self.__limit_control(query.__getitem__)(i)
                except IndexError:
                    break

    def __find_files(self, repo):
        def retrieve(path):
            items = self.__limit_control(repo.get_contents)(path)
            if not isinstance(items, Iterable):
                items = [items]
            for item in items:
                assert self.is_running()
                if item.download_url is not None:
                    if Repository.expects_file(item.path):
                        self._logger.info('      + %s' % item.path)
                        files.append(
                            (item.path, self.__limit_control(bytes.decode)(item.decoded_content))
                        )
                else:
                    folders.append(item.path)

        files, folders = list(), deque()
        retrieve(path='/')
        while True:
            try:
                retrieve(path=folders.popleft())
            except IndexError:
                break
        return files

    def __search(self, time_window):
        self._logger.info('Searching time window: %s' % time_window)
        qualifiers = copy(self._qualifiers)
        qualifiers['created'] = time_window
        query = self._conn.search_repositories(self._keyword, **qualifiers)

        for repo in self.__find_repos(query):
            self._logger.info('* Repository: %s (%s) - %s' % (repo.full_name, repo.id, repo.url))
            newrepo = Repository(repo.full_name)
            newrepo.set_id(repo.id)
            newrepo.set_url(repo.url)

            self._logger.info('  --> Crawling contents...')
            for path, content in self.__find_files(repo):
                newrepo.add_file(path, content)

            self._logger.info('  --> Finding packages...')
            newrepo.find_packages()

            self._logger.info('  --> Saving "%s"...' % repo.full_name)
            newrepo.commit_changes()


class SearchCode:
    def __init__(self, resume=True, search_order='desc', verbose=False):
        reverse = search_order.lower() == 'desc'
        self.slices = TimeSlices(resume=resume, reverse=reverse)

        if verbose:
            self._progress = None
            _log_configurer()
        else:
            total = len(self.slices)
            suffix = 'of %d searches completed' % total
            self._progress = ProgressBar(total, prefix='Searching', suffix=suffix)

        self._run_event = Event()
        self.workers = [
            SearchWorker(user, passwd, self.slices, self._run_event)
            for user, passwd in config.items('credentials')
        ]

        assert self.workers, 'No Github credential found.'

    def run(self):
        assert self.workers, 'No worker to run.'
        for worker in self.workers:
            worker.start()
        self._run_event.set()

    def is_running(self):
        return self._run_event.is_set()

    def stop(self):
        self._run_event.clear()
        self.join_workers()

    def end(self):
        if self.is_running():
            self.stop()
        if self.slices.has_changes():
            self.slices.save()
        if self._progress is not None:
            self._progress.end()

    def join_workers(self):
        for worker in self.workers:
            if worker.is_alive():
                worker.join()

    def raise_worker_exceptions(self):
        for worker in self.workers:
            exc = worker.get_exception()
            if exc:
                raise exc

    def show_progress(self):
        if self._progress is not None:
            self._progress.print()
            while not self.slices.is_completed() and self.is_running():
                self.raise_worker_exceptions()
                self._progress.print(self.slices.remain)
                time.sleep(.1)

    def wait_until_finish(self):
        if self.is_running():
            self.show_progress()
            self.join_workers()
            self.raise_worker_exceptions()
