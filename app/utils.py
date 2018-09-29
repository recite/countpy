# -*- coding: utf-8 -*-
"""
app.utils
~~~~~~~~~

Utilities for the application.
"""

import os
from flask import url_for
from . import app


def template_exists(template):
    return os.path.exists(os.path.join(app.root_path, app.template_folder, template))


def endswith(str1, str2):
    return str1.lower().endswith(str2.lower())


def static_url(filename):
    return url_for('static', filename=filename)


app.jinja_env.tests['endswith'] = endswith
app.jinja_env.filters['static_url'] = static_url
