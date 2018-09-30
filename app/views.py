# -*- coding: utf-8 -*-
"""
app.views
~~~~~~~~~

Rendering application pages.
"""

from copy import deepcopy
from flask import render_template, request, abort, flash
from . import app
from .utils import template_exists, find_packages

DATE_FORMAT = '%Y-%m-%d'
GLOBAL_VARS = {
    'navbar': [
        # (href, caption)
        ('/about', 'About Us'),
        (app.config.get('GITHUB_URL'), 'GitHub'),
        ('/contact', 'Contact Us')
    ],
    'links': [
        # (rel, type, file)
        ('icon', 'image/x-icon', 'img/favicon.ico'),
        ('shortcut icon', 'image/x-icon', 'img/favicon.ico'),
        ('stylesheet', None, 'vendor/bootstrap/dist/css/bootstrap.min.css'),
        ('stylesheet', None, 'vendor/open-iconic/font/css/open-iconic-bootstrap.min.css'),
        ('stylesheet', None, 'css/style.css')
    ],
    'scripts': [
        'vendor/jquery/dist/jquery.slim.min.js',
        'vendor/popper.js/dist/popper.min.js',
        'vendor/bootstrap/dist/js/bootstrap.min.js',
        'js/app.js'
    ]
}


def _render(page_id, **kwargs):
    # Check page template
    template = '%s.html' % page_id
    if not template_exists(template):
        abort(404, 'Page not found')

    # Prepare variables
    variables = deepcopy(GLOBAL_VARS)
    prefix = page_id.upper().replace('-', '_')
    title = app.config.get('%s_PAGE_TITLE' % prefix)
    header = app.config.get('%s_PAGE_HEADER' % prefix)
    if title:
        variables['title'] = title
    if header:
        variables['header'] = header
    variables.update(kwargs)

    # Render template
    return render_template(template, **variables)


@app.route('/', methods=['GET', 'POST'])
def index():
    """Main index page of application. Accepts both GET and POST methods"""

    # Method is POST
    if request.method == 'POST':
        keywords = request.form.get('keywords')
        if keywords:
            return search(keywords)

    # Method is GET or POST with empty data
    return _render('index')


@app.route('/about')
def about():
    """Renders About page"""
    return _render('about')


@app.route('/contact')
def contact():
    """Renders Contact page"""
    return _render('contact')


def search(keywords):
    packages = find_packages(names=keywords.split())
    if packages:
        page_title = app.config.get('INDEX_PAGE_TITLE')
        page_header = app.config.get('INDEX_PAGE_HEADER')
        table_header = app.config.get('SEARCH_RESULT_HEADER_ROW')
        results = [table_header] + [
            (p.name, p.num_repos, p.num_pyfiles, p.num_reqfiles, p.str_updated(DATE_FORMAT))
            for p in packages
        ]
        return _render('result', total=len(packages), title=page_title,
                       header=page_header, keywords=keywords, results=results)

    else:
        flash('No packages found.', 'failed')
        return _render('index', keywords=keywords)
