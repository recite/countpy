# -*- coding: utf-8 -*-

import re
import datetime
from queue import Empty
from multiprocessing import Queue
from collections import deque
from . import config

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

    def __init__(self, total=None, prefix='Progress:',
                 suffix='Complete', decimals=1, length=50):
        self.total = int(total or 0)
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

    def __gen_params(self, complete, total):
        filled_length = int(self.length * complete // total)
        filled_chars = self.__filled_char * filled_length

        empty_length = self.length - filled_length
        empty_chars = self.__empty_char * empty_length

        rate = self.__rate_fmt.format(complete / float(total) * 100)
        bar = '{}{}'.format(filled_chars, empty_chars)
        return dict(bar=bar, rate=rate, **self.params)

    def print(self, complete=0, total=None, **kwargs):
        total = total or self.total
        end = self.__end_char if complete == total else None
        params = self.__gen_params(complete, total)
        params.update(kwargs)
        self.__print_bar(end, **params)

    def end(self):
        if self.__printed and not self.__last_printed:
            print()

    def set_prefix(self, text):
        self.params['prefix'] = str(text)

    def set_suffix(self, text):
        self.params['suffix'] = str(text)


class TaskCounter:
    def __init__(self, tasks=None):
        self._queue = Queue(maxsize=-1)
        self.total = len(tasks)
        for task in tasks:
            self._queue.put_nowait(task)

    @property
    def done(self):
        return self.total - self._queue.qsize()

    def status(self):
        return self.done, self.total

    def get(self):
        try:
            return self._queue.get_nowait()
        except Empty:
            return None


class TimeSlices(TaskCounter):
    def __init__(self, period=None, window=None, reverse=None):
        period = period or config.get('search_period', 'period')
        window = window or config.get('search_period', 'slice')
        reverse = reverse if reverse is not None else config.getboolean(
            'search_period', 'newest_first', fallback=False)
        super(TimeSlices, self).__init__(
            tasks=slice_period(period, window, reverse))
