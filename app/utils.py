# -*- coding: utf-8 -*-
"""
app.utils
~~~~~~~~~

Utilities for the application.
"""

import os
from math import ceil
from flask import url_for, request
from operator import itemgetter
from Levenshtein import distance
from PIL import ImageFont
from . import app
from .models import Package, Repository


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


def url_for_other_page(page):
    args = request.view_args.copy()
    args['page'] = page
    return url_for(request.endpoint, **args)


app.jinja_env.tests['endswith'] = endswith
app.jinja_env.filters['static_url'] = static_url
app.jinja_env.filters['fontwidth'] = fontwidth
app.jinja_env.filters['fontheight'] = fontheight
app.jinja_env.globals['url_for_other_page'] = url_for_other_page


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


def find_packages(names, page, per_page):
    if not isinstance(names, (list, tuple)):
        names = [names]

    found, packages = [], None
    for name in names:
        if Package.exists(name):
            found.append(name)
        else:
            if packages is None:
                packages = Package.query_all(name_only=True, lazy=False)
            if packages:
                similars = find_similars(name, packages)
                found.extend(similars)

    if found:
        s = slice(per_page * page - per_page, per_page * page)
        pagination = Pagination(page, per_page, len(found))
        return [Package(name) for name in sorted(found)[s]], pagination

    return [], None


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


def anchor(href, text=None, **kwargs):
    text = text or href
    attrs = ''
    if kwargs:
        attrs = ' ' + ' '.join('{}="{}"'.format(k, v) for k, v in kwargs.items())
    return '<a href="%s"%s>%s</a>' % (href, attrs, text)


class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count

    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
                    self.page - left_current - 1 < num < self.page + right_current or \
                    num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


def get_pkg_repos(pkgname, page: int, per_page: int):
    if page > 0:
        pkg = find_package(pkgname)
        if pkg and pkg.num_repos > 0:
            s = slice(per_page * page - per_page, per_page * page)
            pagination = Pagination(page, per_page, pkg.num_repos)
            return [Repository(name) for name in sorted(pkg.repos)[s]], pagination
    return [], None


def github_url(url: str):
    return url.replace('api.', '').replace('/repos', '')
