# -*- coding: utf-8 -*-

import re
import os
import pickle
import datetime
from threading import Lock
from collections import deque
from . import _MODULE_DIR, config

__all__ = ['TimeSlices', 'ProgressBar']


# Method for matching time_annotation string
match_time_annotation = re.compile(r'^\s*([1-9]+)?\s*(\w+)\s*$').match


def to_second(time_annotation):
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


def slice_period(period, window, reverse=True):
    """
    Slices time period into time windows. Format each time window (a slice) by
    following the time pattern of Github search API.

    :param str period: a time period to be sliced (time_annotation format)
    :param str window: a time window for slicing (time_annotation format)
    :param bool reverse: reverse order of result list returned
    :return: list of formatted time windows
    :rtype: deque[str]
    """

    period = datetime.timedelta(seconds=to_second(period))
    window = datetime.timedelta(seconds=to_second(window))
    cur_date = datetime.datetime.utcnow().replace(
        microsecond=0, tzinfo=datetime.timezone.utc)
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


class ProgressBar:
    __end_char = '\n'
    __empty_char = '-'
    __filled_char = '█'

    __print_fmt = '\r{prefix} |{bar}| {rate}% {suffix}'

    def __init__(self, total, prefix='Progress:',
                 suffix='Complete', decimals=1, length=50):
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
        period = period or config.get('search_period', 'period')
        window = window or config.get('search_period', 'slice')
        reverse = reverse
        if reverse is None:
            reverse = config.getboolean('search_period', 'newest_first', fallback=False)

        self._resume = resume
        self._datakey = '_'.join('{}:{}'.format(period, window).split())
        self._data = slice_period(period, window, reverse)
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
