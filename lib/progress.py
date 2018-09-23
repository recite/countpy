# -*- coding: utf-8 -*-

__all__ = ['ProgressBar']


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
