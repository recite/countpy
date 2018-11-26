# -*- coding: utf-8 -*-

import re
import datetime
from collections import deque

__all__ = ['slice_period', 'to_second']


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
