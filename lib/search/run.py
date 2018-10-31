# -*- coding: utf-8 -*-

import time
from threading import Event
from . import config, _log_configurer
from .utils import TimeSlices, ProgressBar
from .worker import SearchWorker

__all__ = ['SearchCode']


class SearchCode:
    def __init__(self, resume=True, search_order=None,
                 verbose=False, mode=None, anonymous=False, threads=None):
        reverse = None
        if search_order is not None:
            reverse = search_order.lower() == 'desc'
        self.slices = TimeSlices(resume=resume, reverse=reverse)

        if verbose:
            self._progress = None
            _log_configurer()
        else:
            total = len(self.slices)
            suffix = 'of %d slices done' % total
            self._progress = ProgressBar(total, prefix='Searching', suffix=suffix)

        self._run_event = Event()

        if anonymous:
            threads = int(threads) if threads else 1
            auths = [(None, None)] * threads
        else:
            auths = config.items('credentials')

        self.workers = [
            SearchWorker(user, passwd, self.slices, self._run_event, mode)
            for user, passwd in auths
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
                self._progress.print(self.slices.done)
                time.sleep(.1)

    def wait_until_finish(self):
        if self.is_running():
            self.show_progress()
            self.join_workers()
            self.raise_worker_exceptions()
