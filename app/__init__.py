# -*- coding: utf-8 -*-
"""
app
~~~

Main Flask application for the countpy project
"""

import os, time
from flask import Flask
from redis import StrictRedis
from redis.exceptions import ConnectionError, BusyLoadingError
from multiprocessing import Semaphore

app = Flask(__name__, instance_relative_config=True)
app.secret_key = os.urandom(24)
app.config.from_object('config')

sem = Semaphore(1)
db = StrictRedis(decode_responses=True)


def singlewrite(func):
    def wrapper(*args, **kwargs):
        with sem:
            return func(*args, **kwargs)
    return wrapper


def retrycon(retries=5, delay=5):
    def wrapper(func):
        def wrapped(*args, **kwargs):
            count = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, BusyLoadingError):
                    if count >= retries:
                        raise
                    count += 1
                    time.sleep(delay)
        return wrapped
    return wrapper


from . import utils
from . import views
