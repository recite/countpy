# -*- coding: utf-8 -*-
"""
app.utils
~~~~~~~~~

Utilities for the application.
"""

__all__ = [
    'parse_db_uri'
]


def parse_db_uri(conf):
    """
    Parse input database config into database URI format

    :param conf:    input database config
    :type conf:     dict
    :return:        string of database config in URI format
    :rtype:         str
    """

    # Input config must be a dict
    assert isinstance(conf, dict)

    # Key 'dbname' is required in config
    if 'dbname' not in conf:
        raise ValueError('No database specified')

    # Read and parse config
    dbname = str(conf['dbname'])
    host = str(conf.get('host', '127.0.0.1') or '127.0.0.1')
    port = str(conf.get('port', ''))
    user = str(conf.get('user', ''))
    passwd = str(conf.get('passwd', ''))
    driver = str(conf.get('driver', 'postgresql')).lower() or 'postgresql'

    if user and passwd:
        user = '%s:%s@' % (user, passwd)
    elif user:
        user = '%s@' % user
    elif passwd:
        raise ValueError('No user with that password')

    if port:
        if not port.isdigit():
            raise ValueError('Database port must be a number')
        host = '%s:%s' % (host, port)

    # Return parsed config in URI format
    return '{}://{}{}/{}'.format(driver, user, host, dbname)
