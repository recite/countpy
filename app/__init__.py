# -*- coding: utf-8 -*-
"""
app
~~~

Main Flask application for the countpy project
"""

import os
from flask import Flask
from redis import StrictRedis
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


from . import utils
from . import views
