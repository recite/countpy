# -*- coding: utf-8 -*-
"""
app.models
~~~~~~~~~~

Contains all the model objects and their schemas.
"""

import json
from datetime import datetime
from typing import Dict, Any
from . import db

__all__ = ['Repository']

_KEYSEP = ':'


def _is_notset(variable):
    return variable is None or type(variable) is type(Ellipsis)


def _is_set(variable):
    return not _is_notset(variable)


class HashType:
    _prefix = ''
    _text_fields = ()
    _json_fields = ()
    _date_fields = ('updated',)

    updated = ...  # type: datetime

    @classmethod
    def genkey(cls, name):
        prefix = cls._prefix
        if prefix and not prefix.endswith(_KEYSEP):
            prefix = '{}{}'.format(prefix, _KEYSEP)
        if name.startswith(prefix):
            return name
        return '{}{}'.format(prefix, name)

    @classmethod
    def exists(cls, name):
        return db.exists(cls.genkey(name))

    @classmethod
    def query(cls, name):
        return cls(name) if cls.exists(name) else None

    @classmethod
    def query_all(cls):
        return (cls(name) for name in db.keys(cls.genkey('*')))

    @classmethod
    def set(cls, name, field, value):
        return cls.mset(name, {field: value})

    @classmethod
    def mset(cls, name, mapping):
        assert len(mapping) > 0, 'Nothing to set.'
        now = datetime.utcnow()
        mapping['updated'] = now
        db.hmset(cls.genkey(name), {k: cls.store_val(v, k) for k, v in mapping.items()})
        return now

    @classmethod
    def get(cls, name, field):
        return cls.use_val(db.hget(cls.genkey(name), field), field)

    @classmethod
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
            if field in cls._text_fields:
                return str(value)
            elif field in cls._json_fields:
                return json.dumps(value)
            elif field in cls._date_fields:
                if isinstance(value, datetime):
                    return str(value.timestamp())
                elif isinstance(value, (float, int, str)):
                    return value
        raise NotImplementedError('Unsupported field "%s" with value "%s"' % (field, value))

    @classmethod
    def use_val(cls, value, field):
        if field in cls._text_fields:
            return value
        elif field in cls._json_fields:
            if _is_set(value):
                return json.loads(value)
            return None
        elif field in cls._date_fields:
            if _is_set(value):
                return datetime.utcfromtimestamp(float(value))
            return None
        raise NotImplementedError('Unsupported field "%s" with value "%s"' % (field, value))

    @classmethod
    def all_fields(cls):
        return cls._text_fields + cls._json_fields + cls._date_fields

    def __new__(cls, name, **attrs):
        if attrs:
            if cls.exists(name):
                raise IOError('Already existed, only accepts "name" for init %s.' % cls)
            assert set(attrs.keys()) <= set(cls.all_fields())
        return object.__new__(cls)

    def __init__(self, name, **attrs):
        self.name = name
        self.__cache(**attrs)
        self.__load()

    def __str__(self):
        return '%s(name=%s)' % (self.__class__.__name__, self.name)

    def __repr__(self):
        return str(self)

    def __load(self):
        for field, value in self.getall(self.name).items():
            if hasattr(self, field) and _is_set(getattr(self, field)):
                continue
            setattr(self, field, value)

    def __cache(self, **attrs):
        if attrs:
            for field, value in attrs.items():
                setattr(self, field, value)

    def commit(self):
        mapping = {}
        for field in self.all_fields():
            if hasattr(self, field):
                value = getattr(self, field)
                if _is_set(value):
                    mapping[field] = value
        if mapping:
            self.updated = self.mset(self.name, mapping)

    def is_existed(self):
        return self.exists(self.name)


class Repository(HashType):
    _prefix = 'repo'
    _text_fields = ('id', 'url')
    _json_fields = ('pyfiles', 'reqfile')

    reqfile = ...  # type: Dict[Any, Any]
    pyfiles = ...  # type: Dict[Any, Any]

    def add_pyfile(self, path, content):
        if _is_notset(self.pyfiles):
            self.pyfiles = {}
        self.pyfiles[path] = content

    def set_reqfile(self, path, content):
        self.reqfile = {path: content}
