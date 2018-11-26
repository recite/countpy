# -*- coding: utf-8 -*-

import time
from multiprocessing import Process
from app.models import Repository
from modules.github.endpoints import SearchRepositories
from modules.github.client import ContentRetriever
from modules.logger import get_logger, client_configurer
from . import config

__all__ = ['SearchWorker']


class SearchWorker(Process):
    _keyword = config.get('search_repo_params', 'keyword', fallback='')
    _sort = config.get('search_repo_params', 'sort', fallback=None)
    _order = config.get('search_repo_params', 'order', fallback=None)
    _per_page = config.getint('search_repo_params', 'per_page', fallback=None)
    _qualifiers = config.getdict('search_repo_params', 'qualifiers', fallback={})
    _timeout = config.getint('search_repo_params', 'timeout', fallback=None)

    _repo_fmt = '* {label} repository: {full_name} ({id}) - {url}'

    def __init__(self, user, passwd, slices, repos,
                 event, log_queue=None, exc_queue=None):
        super(SearchWorker, self).__init__(name=user)
        self._logger = None
        self._slices = slices
        self._repos = repos
        self._event = event
        self._log_queue = log_queue
        self._exc_queue = exc_queue
        self._search = None
        self._retriever = None

        auth = (user, passwd) if user else None

        if self._slices is not None:
            self._search = SearchRepositories(
                keyword=self._keyword,
                qualifiers=self._qualifiers,
                sort=self._sort,
                order=self._order,
                per_page=self._per_page,
                auth=auth,
                timeout=self._timeout
            )

        if self._repos is not None:
            self._retriever = ContentRetriever(auth=auth)

    def is_running(self):
        return self._event.is_set()

    def run(self):
        # Configure logging
        if self._log_queue is not None:
            client_configurer(self._log_queue)
        self._logger = get_logger(self.name)

        # Run worker
        self._event.wait()
        self._logger.info('Search worker (%s) is started' % self.name)

        try:
            self.search_repos()
            self.retrieve_files()
        except AssertionError:
            pass
        except Exception as exc:
            self._logger.exception(exc)
            if self._exc_queue is not None:
                self._exc_queue.put((self.name, exc))

        self._logger.info('Search worker (%s) is stopped.' % self.name)

    def search_repos(self):
        if self._search is not None:
            while self._event.is_set():
                time_slice = self._slices.get()
                if time_slice is None:
                    break
                self.search_repos_in_slice(time_slice)

    def retrieve_files(self):
        if self._retriever is not None:
            self._logger.info('Retrieving repositories\'s contents...')
            time.sleep(1)
            while self._event.is_set():
                repo_name = self._repos.get()
                if repo_name is None:
                    break
                self.retrieve_files_in_repo(repo_name)

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

            # Newly create repo in database
            newrepo = Repository(repo.full_name)
            newrepo.set_id(repo.id)
            newrepo.set_url(repo.url)
            newrepo.set_contents_url(repo.contents_url)
            newrepo.commit_changes()

            # Queue repository for later retrieving
            if self._repos is not None:
                self._repos.put(repo.full_name)

    def retrieve_files_in_repo(self, repo_name):
        repo = Repository(repo_name)

        # Skip if repository was done already
        if repo.retrieved:
            self._logger.info(self._repo_fmt.format(
                label='Already done:', full_name=repo.name,
                id=repo.id, url=repo.url))
            return

        # Skip if repository has no contents URL
        if not repo.contents_url:
            self._logger.info(self._repo_fmt.format(
                label='No contents URL found:', full_name=repo.name,
                id=repo.id, url=repo.url))
            return

        # Do retrieving contents from GitHub
        self._logger.info(self._repo_fmt.format(
            label='Retrieving:', full_name=repo.name, id=repo.id, url=repo.url))

        added = False
        for file in self._retriever.traverse(repo.contents_url):
            assert self.is_running()
            if not Repository.expects_file(file.path):
                self._logger.info('  (-) %s' % file.path)
                continue
            self._logger.info('  (+) %s' % file.path)
            self._retriever.retrieve_content(file)
            repo.add_file(file.path, file.decoded_content)
            if not added:
                added = True

        # Find packages if files found
        if added:
            self._logger.info('  --> Finding packages...')
            repo.find_packages()

        # Do nothing if no file found
        else:
            self._logger.info('  --> No expected files found.')

        # Save repository
        self._logger.info('  --> Saving repository...')
        repo.set_retrieved(True)
        repo.commit_changes()
