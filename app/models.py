# -*- coding: utf-8 -*-
"""
app.models
~~~~~~~~~~

Contains all the model objects and their schemas.
"""

import os
import re
import json
import time
from functools import partial
from datetime import datetime
from typing import Set, List, Dict, DefaultDict
from collections import namedtuple, defaultdict
from . import app, db, singlewrite, retrycon

__all__ = ['Repository', 'Package', 'Snapshot']

_KEYSEP = ':'

RepoFile = namedtuple('RepoFile', 'path content')


def _is_notset(variable):
    return variable is None or type(variable) is type(Ellipsis)


def _is_set(variable):
    return not _is_notset(variable)


class HashType:
    _prefix = ''

    _num_fields = ()
    _text_fields = ('name',)
    _json_fields = ()
    _date_fields = ('updated',)

    _defaults = {}

    updated = ...  # type: datetime

    @classmethod
    def _get_default(cls, field):
        value = cls._defaults.get(field)
        return value() if callable(value) else value

    @classmethod
    def genkey(cls, name):
        prefix = cls._prefix
        if prefix and not prefix.endswith(_KEYSEP):
            prefix = '{}{}'.format(prefix, _KEYSEP)
        if name.startswith(prefix):
            name = name.replace(prefix, '')
        return '{}{}'.format(prefix, name.lower())

    @staticmethod
    def no_prefix(key):
        return key.split(_KEYSEP, maxsplit=1)[-1]

    @classmethod
    @retrycon()
    def exists(cls, name):
        return db.exists(cls.genkey(name))

    @classmethod
    def query(cls, name):
        return cls(name) if cls.exists(name) else None

    @classmethod
    @retrycon()
    def query_all(cls, name_only=False, lazy=True):
        parser = cls.no_prefix if name_only else cls
        ret = (parser(key) for key in db.keys(cls.genkey('*')))
        return ret if lazy else list(ret)

    @classmethod
    def set(cls, name, field, value):
        return cls.mset(name, {field: value})

    @classmethod
    @singlewrite
    @retrycon()
    def mset(cls, name, mapping):
        assert len(mapping) > 0, 'Nothing to set.'
        now = datetime.utcnow()
        mapping['updated'] = now
        db.hmset(cls.genkey(name), {k: cls.store_val(v, k) for k, v in mapping.items()})
        return now

    @classmethod
    @retrycon()
    def get(cls, name, field):
        return cls.use_val(db.hget(cls.genkey(name), field), field)

    @classmethod
    @retrycon()
    def mget(cls, name, fields):
        assert set(fields) <= set(cls.all_fields()), 'Unknown field found in %s' % fields
        values = db.hmget(cls.genkey(name), fields)
        return tuple(cls.use_val(v, fields[i]) for i, v in enumerate(values))

    @classmethod
    def getall(cls, name):
        fields = cls.all_fields()
        values = cls.mget(name, fields)
        return dict(zip(fields, values))

    @classmethod
    def store_val(cls, value, field):
        if _is_set(value):
            if field in cls._text_fields or field in cls._num_fields:
                return str(value)
            elif field in cls._json_fields:
                return json.dumps(list(value) if isinstance(value, set) else value)
            elif field in cls._date_fields:
                if isinstance(value, datetime):
                    return str(value.timestamp())
                elif isinstance(value, (float, int, str)):
                    return str(value)
        raise NotImplementedError('Unsupported field "%s" with value "%s"' % (field, value))

    @classmethod
    def use_val(cls, value, field):
        if field in cls._text_fields:
            return value if _is_set(value) else cls._get_default(field)
        elif field in cls._num_fields:
            return int(value) if _is_set(value) else cls._get_default(field)
        elif field in cls._json_fields:
            return json.loads(value) if _is_set(value) else cls._get_default(field)
        elif field in cls._date_fields:
            return datetime.utcfromtimestamp(float(value)) if _is_set(value) else cls._get_default(field)
        raise NotImplementedError('Unsupported field "%s" with value "%s"' % (field, value))

    @classmethod
    def all_fields(cls):
        return cls._num_fields + cls._text_fields + cls._json_fields + cls._date_fields

    def str_updated(self, fmt):
        if _is_set(self.updated):
            return self.updated.strftime(fmt)
        return ''

    def __new__(cls, name, **attrs):
        if attrs:
            if cls.exists(name):
                raise IOError('Already existed, only accepts "name" for init %s.' % cls)
            assert set(attrs.keys()) <= set(cls.all_fields())
        instance = object.__new__(cls)
        instance._changes = set()
        instance._existed = False
        return instance

    def __init__(self, name, **attrs):
        self.name = name.lower()
        self.__cache(**attrs)
        self.__load()

    def __str__(self):
        return '%s(name=%s)' % (self.__class__.__name__, self.name)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return other.storekey == self.storekey
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.storekey)

    def __cache(self, **attrs):
        if attrs:
            for field, value in attrs.items():
                setattr(self, field, value)
                self.set_change(field)

    def __load(self):
        for field, value in self.getall(self.name).items():
            if field == 'name':
                if value is None:
                    self.set_change('name')
                else:
                    self._existed = True
                continue
            elif self.is_changed(field):
                continue
            setattr(self, field, value if _is_set(value) else self._get_default(field))

    @property
    def storekey(self):
        return self.genkey(self.name)

    def has_changes(self):
        return len(self._changes) > 0

    def is_changed(self, field):
        return field in self._changes

    def set_change(self, *fields):
        self._changes.update(fields)

    def __commit(self, fields):
        mapping = {}
        for field in fields:
            if hasattr(self, field):
                value = getattr(self, field)
                if _is_set(value):
                    mapping[field] = value
        if mapping:
            self.updated = self.mset(self.name, mapping)
            if not self._existed:
                self._existed = True

    def commit_changes(self):
        if self.has_changes():
            self.__commit(fields=self._changes)

    def commit_all(self):
        self.__commit(fields=self.all_fields())

    def is_existed(self):
        return self._existed


class RepoFiles:
    _pyfile = 'pyfile'
    _reqfile = 'reqfile'

    _ftypes = (_pyfile, _reqfile)

    _find_lines = {
        _pyfile: re.compile(r'(?:^|\n)\s*((?:import|from).+?(?<!\\)(?=\n|$))', flags=re.DOTALL).findall,
        _reqfile: re.compile(r'(?:^|\n)\s*(?!#)\s*([^\s].+?)(?<!\\)(?= #|\n|$)', flags=re.DOTALL).findall
    }

    _find_packages = {
        _pyfile: re.compile(
            r'(?:^|\n)\s*(?:from|import) +(.+?)(?= +import|(?<!\\)\n|$)', flags=re.DOTALL).findall,

        _reqfile: re.compile(
            r'(?:^|\n)\s*(\w[\w-]+)(?:\s*\[[\w\s,-]+\])?'
            r'(\s*[!~<=>]{1,2}\s*\d+(?:\.\d+)*(?:\s*,\s*[!~<=>]{1,2}\s*\d+(?:\.\d+)*)*)?', flags=re.DOTALL).findall
    }

    @staticmethod
    def is_pyfile(path):
        return path.lower().endswith('.py')

    @staticmethod
    def is_reqfile(path):
        fname = os.path.basename(path)
        return fname.lower() == 'requirements.txt'

    @staticmethod
    def pkgname_from_path(path):
        dirs, base = os.path.dirname(path), os.path.basename(path)
        if dirs in ('', '/'):
            pkgname = os.path.splitext(base)[0] if RepoFiles.is_pyfile(base) else base
        else:
            dirs = dirs.split(os.path.sep)
            pkgname = dirs[0] or dirs[1]
        return pkgname.lower()

    @classmethod
    def get_ftype(cls, path):
        if cls.is_pyfile(path):
            return cls._pyfile
        elif cls.is_reqfile(path):
            return cls._reqfile
        return None

    @classmethod
    def retract_content(cls, content, ftype):
        assert ftype in cls._ftypes, 'Unknown ftype "%s"' % ftype
        finder = cls._find_lines.get(ftype)
        return '\n'.join(finder(content))

    @classmethod
    def parse_pyfile(cls, content):
        finder = cls._find_packages[cls._pyfile]
        ret = set()
        for found in finder(content):
            if not found.strip().startswith('.'):
                for part in found.split(','):
                    pkgname = part.rsplit('as', maxsplit=1)[0].split('.', maxsplit=1)[0]
                    ret.add(pkgname.strip().lower())
        return ret

    @classmethod
    def parse_reqfile(cls, content):
        finder = cls._find_packages[cls._reqfile]
        return {pkgname.strip().lower(): version.strip() for pkgname, version in finder(content)}

    def local_packages(self):
        return set(self.pkgname_from_path(path) for path, _ in self.get_pyfiles())

    @classmethod
    def __struct_init(cls, other_struct):
        if _is_notset(other_struct):
            return {cls._pyfile: dict(), cls._reqfile: dict()}
        elif isinstance(other_struct, dict):
            if set(other_struct.keys()) == set(cls._ftypes):
                if all(isinstance(other_struct[i], dict) for i in cls._ftypes):
                    return other_struct
        elif isinstance(other_struct, cls):
            return other_struct.as_dict()
        raise TypeError('Unsupported struct: %r' % other_struct)

    def as_dict(self):
        return self._files

    def __init__(self, files=None):
        self._files = self.__struct_init(files)

    def __iter__(self):
        for file in self.get_pyfiles():
            yield file
        if self.reqfile:
            yield self.reqfile

    def __getitem__(self, path):
        ftype = self.get_ftype(path)
        if ftype is not None:
            return self._files[ftype][path]
        raise KeyError(path)

    def __setitem__(self, path, content):
        ftype = self.get_ftype(path)
        if ftype is None:
            raise KeyError(path)
        content = self.retract_content(content, ftype)
        if ftype == self._pyfile:
            self._files[ftype][path] = content
        elif ftype == self._reqfile:
            self._files[ftype] = {path: content}
        else:
            raise NotImplementedError

    def __contains__(self, path):
        ftype = self.get_ftype(path)
        if ftype is not None:
            return path in self._files[ftype]
        return False

    def get_pyfiles(self):
        yield from (RepoFile(*i) for i in self._files[self._pyfile].items())

    @property
    def reqfile(self):
        try:
            return RepoFile(*next(iter(self._files[self._reqfile].items())))
        except StopIteration:
            return None


class Package(HashType):
    _prefix = 'pkg'

    _num_fields = ('num_pyfiles', 'num_reqfiles', 'num_repos')
    _json_fields = ('pyfiles', 'reqfiles', 'repos')

    _defaults = {
        'num_pyfiles': 0,
        'num_reqfiles': 0,
        'num_repos': 0,
        'repos': set,
        'reqfiles': dict,
        'pyfiles': partial(defaultdict, set)
    }

    num_repos = ...  # type: int
    num_pyfiles = ...  # type: int
    num_reqfiles = ...  # type: int

    repos = ...  # type: Set[str]
    reqfiles = ...  # type: Dict[str, str]
    pyfiles = ...  # type: DefaultDict[str, Set[str]]

    @classmethod
    def use_val(cls, value, field):
        value = super(Package, cls).use_val(value, field)
        if field == 'repos':
            return set(value)
        elif field == 'pyfiles':
            return defaultdict(set, {k: set(v) for k, v in value.items()})
        return value

    @classmethod
    def store_val(cls, value, field):
        if field == 'pyfiles':
            value = {k: list(v) for k, v in value.items()}
        return super(Package, cls).store_val(value, field)

    def add_repo(self, repo):
        if repo not in self.repos:
            self.repos.add(repo)
            self.num_repos += 1
            self.set_change('repos', 'num_repos')

    def add_pyfile(self, path, repo):
        self.add_repo(repo)
        if path not in self.pyfiles[repo]:
            self.pyfiles[repo].add(path)
            self.num_pyfiles += 1
            self.set_change('pyfiles', 'num_pyfiles')

    def add_pkgver(self, version, repo):
        self.add_repo(repo)
        if repo not in self.reqfiles:
            self.reqfiles[repo] = version
            self.num_reqfiles += 1
            self.set_change('reqfiles', 'num_reqfiles')
        else:
            self.reqfiles[repo] = version
            self.set_change('reqfiles')

    def has_reqfile(self, repo):
        return repo in self.reqfiles

    def get_pkgver(self, repo):
        return self.reqfiles.get(repo)


class Repository(HashType):
    _prefix = 'repo'
    _num_fields = ('retrieved',)
    _text_fields = ('name', 'id', 'url', 'contents_url')
    _json_fields = ('files', 'packages')

    _defaults = {
        'files': RepoFiles,
        'packages': [],
        'retrieved': False
    }

    id = ...  # type: str
    url = ...  # type: str
    contents_url = ...  # type: str
    retrieved = ...  # type: bool
    files = ...  # type: RepoFiles
    packages = ...  # type: List[str]

    @classmethod
    def use_val(cls, value, field):
        value = super(Repository, cls).use_val(value, field)
        if field == 'files':
            return value if isinstance(value, RepoFiles) else RepoFiles(value)
        elif field == 'retrieved':
            return bool(value)
        else:
            return value

    @classmethod
    def store_val(cls, value, field):
        if field == 'files':
            value = value.as_dict()
        elif field == 'retrieved':
            value = 1 if value is True else 0
        return super(Repository, cls).store_val(value, field)

    @staticmethod
    def expects_file(path):
        return RepoFiles.is_pyfile(path) or RepoFiles.is_reqfile(path)

    @property
    def full_name(self):
        return self.name

    def exists_file(self, path):
        return path in self.files

    def get_content(self, path):
        try:
            return self.files[path]
        except KeyError:
            return None

    def set_id(self, id_):
        if id_ != self.id:
            self.id = id_
            self.set_change('id')

    def set_url(self, url):
        if url != self.url:
            self.url = url
            self.set_change('url')

    def set_contents_url(self, contents_url):
        if contents_url != self.contents_url:
            self.contents_url = contents_url
            self.set_change('contents_url')

    def set_retrieved(self, value):
        value = bool(value)
        if value != self.retrieved:
            self.retrieved = value
            self.set_change('retrieved')

    def add_file(self, path, content):
        try:
            self.files[path] = content
        except KeyError:
            return False
        else:
            self.set_change('files')
            return True

    def find_packages(self):
        ext_packages = {}
        local_packages = self.files.local_packages()

        # Find packages in python modules
        for path, content in self.files.get_pyfiles():
            packages = RepoFiles.parse_pyfile(content)
            for pkgname in packages - local_packages:
                if pkgname:
                    pkg = ext_packages.get(pkgname) or Package(pkgname)
                    pkg.add_pyfile(path, self.name)
                    if pkgname not in ext_packages:
                        ext_packages[pkgname] = pkg

        # Find packages in requirement file
        if _is_set(self.files.reqfile):
            _, content = self.files.reqfile
            packages = RepoFiles.parse_reqfile(content)
            for pkgname, version in packages.items():
                if pkgname and pkgname not in local_packages:
                    pkg = ext_packages.get(pkgname) or Package(pkgname)
                    pkg.add_pkgver(version, self.name)
                    if pkgname not in ext_packages:
                        ext_packages[pkgname] = pkg

        # Commit packages' changes
        for pkg in ext_packages.values():
            pkg.commit_changes()

        # Store package name in repo
        self.packages = list(ext_packages.keys())
        self.set_change('packages')

    def query_packages(self):
        yield from (Package(i) for i in self.packages)


class Snapshot:
    def __init__(self, interval=None):
        self.interval = int(interval or app.config.get('REDIS_SAVE_INTERVAL'))
        self._lastsave = time.time()

    @property
    def elapse(self):
        return time.time() - self._lastsave

    @property
    def remain(self):
        delta = self.interval - self.elapse
        return delta if delta > 0 else 0

    @singlewrite
    @retrycon()
    def _do_save(self):
        db.save()

    def saveable(self):
        return self.elapse >= self.interval

    def wait(self):
        if not self.saveable():
            time.sleep(self.remain)

    def save(self, force=False):
        if force or self.saveable():
            self._do_save()
            self._lastsave = time.time()
