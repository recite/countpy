# -*- coding: utf-8 -*-

import time
from queue import Empty
from multiprocessing import Event, Queue
from modules.logger import LogServer
from . import config
from .utils import TaskCounter, TimeSlices, ProgressBar
from .worker import SearchWorker
from app.models import Repository

__all__ = ['SearchCode']


class SearchCode:
    def __init__(self, search_order=None, verbose=False, mode=None,
                 anonymous=False, threads=None, logfile=None):
        self.slices = None
        self.repos = None
        self._run_event = Event()

        # Prepare search time slices
        mode = mode or 'both'
        if mode == 'both' or mode == 'search-only':
            reverse = search_order.lower() == 'desc' if search_order else None
            self.slices = TimeSlices(reverse=reverse)

        # Query all local repositories
        if mode == 'both' or mode == 'retrieve-only':
            self.repos = TaskCounter(
                tasks=Repository.query_all(name_only=True, lazy=False))

        # Verbose or show progress
        self._progress = None if verbose else ProgressBar()

        # Anonymous or authentic
        if anonymous:
            threads = int(threads) if threads else 1
            auths = [(None, None)] * threads
        else:
            auths = config.items('credentials')
            assert auths, 'No Github credential found'

        # Init queues
        self._log_queue = Queue()
        self._exc_queue = Queue()

        # Init log server
        self.logsrv = LogServer(self._log_queue, verbose, logfile)

        # Init search workers
        self.workers = [
            SearchWorker(user, passwd, self.slices, self.repos,
                         self._run_event, self._log_queue, self._exc_queue)
            for user, passwd in auths
        ]

    def run(self):
        assert self.workers, 'No worker to run'
        self.logsrv.start()
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
        if self._progress is not None:
            self._progress.end()
        if self.logsrv.is_alive():
            self._log_queue.put(None)
            self.logsrv.join()

    def join_workers(self):
        for worker in self.workers:
            if worker.is_alive():
                worker.join()

    def raise_worker_exceptions(self):
        try:
            _, exc = self._exc_queue.get_nowait()
        except Empty:
            return
        else:
            self.end()
            raise exc

    def show_progress(self):
        def _show(haystack, prefix, suffix):
            self._progress.set_prefix(prefix)
            self._progress.set_suffix('of %s %s' % (haystack.total, suffix))
            while self.is_running():
                done, total = haystack.status()
                if done == total:
                    break
                self._progress.print(done, total)
                self.raise_worker_exceptions()
                time.sleep(.5)

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
