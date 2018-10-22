# -*- coding: utf-8 -*-

import time
from threading import Thread
from app.models import Repository
from lib.github.endpoints import SearchRepositories
from lib.github.client import ContentRetriever
from . import config, _get_logger

__all__ = ['SearchWorker']


class SearchWorker(Thread):
    _keyword = config.get('search_repo_params', 'keyword', fallback='')
    _sort = config.get('search_repo_params', 'sort', fallback=None)
    _order = config.get('search_repo_params', 'order', fallback=None)
    _per_page = config.getint('search_repo_params', 'per_page', fallback=None)
    _qualifiers = config.getdict('search_repo_params', 'qualifiers', fallback={})
    _timeout = config.getint('search_repo_params', 'timeout', fallback=None)

    _repo_fmt = '* {label} repository: {full_name} ({id}) - {url}'

    def __init__(self, user, passwd, slices, event, mode=None):
        super(SearchWorker, self).__init__(name=user)
        self._logger = _get_logger(self.__class__.__name__)
        self._slices = slices
        self._event = event
        self._exception = None
        self._search = None
        self._retriever = None

        mode = mode or 'both'
        auth = (user, passwd) if user else None

        if mode == 'both' or mode == 'search-only':
            self._search = SearchRepositories(
                keyword=self._keyword,
                qualifiers=self._qualifiers,
                sort=self._sort,
                order=self._order,
                per_page=self._per_page,
                auth=auth,
                timeout=self._timeout
            )

        if mode == 'both' or mode == 'retrieve-only':
            self._retriever = ContentRetriever(auth=auth)

    def get_exception(self):
        return self._exception

    def is_running(self):
        return self._event.is_set()

    def run(self):
        self._event.wait()
        self._logger.info('Search worker (%s) is started' % self.name)
        try:
            self.search_repos()
            self.retrieve_files()
        except AssertionError:
            pass
        except Exception as exc:
            self._exception = exc
            raise
        self._logger.info('Search worker (%s) is stopped.' % self.name)

    def search_repos(self):
        if self._search is None:
            return

        while self._event.is_set():
            time_slice = self._slices.get()
            if time_slice is None:
                break
            self.search_repos_in_slice(time_slice)
            self._slices.done(time_slice)

    def search_repos_in_slice(self, time_slice):
        self._logger.info('Searching time slice: %s' % time_slice)
        self._search.search(created=time_slice)
        for repo in self._search.traverse():
            assert self.is_running()
            if Repository.exists(repo.full_name):
                self._logger.info(
                    self._repo_fmt.format(label='Existed', **repo.__dict__))
                continue
            self._logger.info(
                self._repo_fmt.format(label='Found', **repo.__dict__))
            newrepo = Repository(repo.full_name)
            newrepo.set_id(repo.id)
            newrepo.set_url(repo.url)
            newrepo.set_contents_url(repo.contents_url)
            newrepo.commit_changes()

    def retrieve_files(self):
        if self._retriever is None:
            return

        self._logger.info('Retrieving contents for all repositories in DB...')
        time.sleep(1)

        for repo in Repository.query_all():
            assert self.is_running()
            if repo.retrieved:
                self._logger.info(
                    self._repo_fmt.format(
                        label='Already done', full_name=repo.name,
                        id=repo.id, url=repo.url))
                continue

            self._logger.info(self._repo_fmt.format(
                label='Retrieving', full_name=repo.name, id=repo.id, url=repo.url))

            if not repo.contents_url:
                self._logger.info('  --> No contents URL.')
                continue

            for file in self._retriever.traverse(repo.contents_url):
                if not Repository.expects_file(file.path):
                    self._logger.info('  (-) %s' % file.path)
                    continue
                self._logger.info('  (+) %s' % file.path)
                repo.add_file(file.path, file.content)

            self._logger.info('  --> Finding packages...')
            repo.find_packages()
            self._logger.info('  --> Saving repository...')
            repo.commit_changes()
