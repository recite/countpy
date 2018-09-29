# -*- coding: utf-8 -*-
"""
app
~~~

Main Flask application for the countpy project
"""

import os
from flask import Flask
from redis import StrictRedis

app = Flask(__name__, instance_relative_config=True)
app.secret_key = os.urandom(24)
app.config.from_object('config')
db = StrictRedis(decode_responses=True)

from . import utils
from . import views
