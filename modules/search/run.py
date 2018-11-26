# -*- coding: utf-8 -*-

from queue import Empty
from multiprocessing import Event, Queue
from modules.logger import LogServer
from . import config
from .utils import slice_period
from .worker import SearchWorker
from app.models import Repository

__all__ = ['SearchCode']


class SearchCode:
    def __init__(self, search_order=None, verbose=False, mode=None,
                 anonymous=False, threads=None, logfile=None):
        self.slices = None
        self.repos = None
        self._run_event = Event()

        # Anonymous or authentic
        if anonymous:
            threads = int(threads) if threads else 1
            auths = [(None, None)] * threads
        else:
            auths = config.items('credentials')
            assert auths, 'No Github credential found'

        # Prepare search time slices
        mode = mode or 'both'
        if mode == 'both' or mode == 'search-only':
            self.slices = Queue()
            period = config.get('search_period', 'period')
            window = config.get('search_period', 'slice')
            reverse = search_order.lower() == 'desc' if search_order else None
            for time_slice in slice_period(period, window, reverse):
                self.slices.put_nowait(time_slice)

        # Query all local repositories
        if mode == 'both' or mode == 'retrieve-only':
            self.repos = Queue()
            for repo in Repository.query_all(name_only=True):
                self.repos.put_nowait(repo)

        # Init log server
        self._log_queue = Queue()
        self.logsrv = LogServer(self._log_queue, verbose, logfile)

        # Init search workers
        self._exc_queue = Queue()
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
        if self.slices:
            self.slices.put_nowait(None)
        if self.repos:
            self.repos.put_nowait(None)
        self.join_workers()

    def end(self):
        if self.is_running():
            self.stop()
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

    def wait_until_finish(self):
        if self.is_running():
            self.join_workers()
            self.raise_worker_exceptions()
