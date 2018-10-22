# -*- coding: utf-8 -*-

from .client import GithubSearch

__all__ = ['SearchRepositories']


class SearchRepositories(GithubSearch):
    def __init__(self, **kwargs):
        super(SearchRepositories, self).__init__(
            endpoint='search_repositories', **kwargs)
