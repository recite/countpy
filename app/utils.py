# -*- coding: utf-8 -*-
"""
app.utils
~~~~~~~~~

Utilities for the application.
"""

import os
from flask import url_for
from operator import itemgetter
from Levenshtein import distance
from PIL import ImageFont
from . import app
from .models import Package


def endswith(str1, str2):
    return str1.lower().endswith(str2.lower())


def static_url(filename):
    return url_for('static', filename=filename)


def fontsize(text, font='DejaVuSans', size=11):
    size = int(size) if size else 10
    if font and not font.lower().endswith('.ttf'):
        font += '.ttf'
    try:
        font = ImageFont.truetype(font, size)
    except (AttributeError, OSError):
        font = ImageFont.load_default()

    return font.getsize(text)


def fontwidth(text, font='DejaVuSans', size=11):
    return fontsize(text, font, size)[0]


def fontheight(text, font='DejaVuSans', size=11):
    return fontsize(text, font, size)[-1]


app.jinja_env.tests['endswith'] = endswith
app.jinja_env.filters['static_url'] = static_url
app.jinja_env.filters['fontwidth'] = fontwidth
app.jinja_env.filters['fontheight'] = fontheight


def template_exists(template):
    return os.path.exists(os.path.join(app.root_path, app.template_folder, template))


def find_similars(needle, haystack):
    max_distance = app.config.get('MAX_EDIT_DISTANCE', 0)
    normalize = lambda x: x.lower()
    distances = ((value, distance(normalize(needle), normalize(value))) for value in haystack)
    candidates = filter(lambda x: x[1] <= max_distance, distances)
    return [x[0] for x in sorted(candidates, key=itemgetter(1))]


def find_package(name):
    if Package.exists(name):
        return Package(name)
    return None


def find_packages(names):
    assert isinstance(names, (list, tuple))
    found = []
    packages = None
    for name in names:
        if Package.exists(name):
            found.append(Package(name))
        else:
            if packages is None:
                packages = Package.query_all(name_only=True, lazy=False)
            if packages:
                similars = find_similars(name, packages)
                if similars:
                    found.extend([Package(name) for name in similars])
    return found


def beautinum(num, decimals=None):
    num = round(num, decimals or 0)
    if str(num).endswith('.0'):
        return int(num)
    return num


def shortnum(num, decimals=2):
    num = float(num)
    if num > 1000000:
        return '%sM' % beautinum(num/1000000, decimals)
    elif num > 1000:
        return '%sK' % beautinum(num / 1000, decimals)
    else:
        return str(beautinum(num))
