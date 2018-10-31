# -*- coding: utf-8 -*-

import time
from threading import Event
from . import config, _log_configurer
from .utils import TaskCounter, TimeSlices, ProgressBar
from .worker import SearchWorker
from app.models import Repository

__all__ = ['SearchCode']


class SearchCode:
    def __init__(self, resume=True, search_order=None, verbose=False,
                 mode=None, anonymous=False, threads=None, logfile=None):
        self.slices = None
        self.repos = None
        self._run_event = Event()

        # Prepare search time slices
        mode = mode or 'both'
        if mode == 'both' or mode == 'search-only':
            reverse = None
            if search_order is not None:
                reverse = search_order.lower() == 'desc'
            self.slices = TimeSlices(resume=resume, reverse=reverse)

        # Query all local repositories
        if mode == 'both' or mode == 'retrieve-only':
            self.repos = TaskCounter(
                tasks=Repository.query_all(name_only=True, lazy=False))

        # Verbose or show progress
        _log_configurer(verbose, logfile)
        self._progress = None if verbose else ProgressBar()

        # Anonymous or authentic
        if anonymous:
            threads = int(threads) if threads else 1
            auths = [(None, None)] * threads
        else:
            auths = config.items('credentials')
            assert auths, 'No Github credential found'

        # Init search workers
        self.workers = [
            SearchWorker(user, passwd, self.slices, self.repos, self._run_event)
            for user, passwd in auths
        ]

    def run(self):
        assert self.workers, 'No worker to run'
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
        def _show(haystack, prefix, suffix):
            self._progress.set_prefix(prefix)
            self._progress.set_suffix('of %s %s' % (haystack.total, suffix))
            while not haystack.is_completed() and self.is_running():
                done, total = haystack.status()
                self._progress.print(done, total)
                self.raise_worker_exceptions()
                time.sleep(.1)

        if self._progress is not None:
            if self.slices is not None:
                _show(self.slices, 'Search repositories:', 'time slices')
            if self.repos is not None:
                _show(self.repos, 'Retrieve contents  :', 'repositories')

    def wait_until_finish(self):
        if self.is_running():
            self.show_progress()
            self.join_workers()
            self.raise_worker_exceptions()
