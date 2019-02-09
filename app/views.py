# -*- coding: utf-8 -*-
"""
app.views
~~~~~~~~~

Rendering application pages.
"""

from copy import deepcopy
from urllib.parse import quote, unquote
from flask import render_template, request, \
    abort, flash, Response, url_for, redirect
from . import app
from .utils import template_exists, find_packages, \
    find_package, anchor, get_pkg_repos, github_url

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

PER_PAGE = app.config.get('PER_PAGE')
DATE_FORMAT = '%Y-%m-%d'


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
            return redirect(url_for('result', keywords=quote(keywords)))

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


@app.route('/badge/<pkgname>')
def badge(pkgname):
    pkg = find_package(pkgname)
    if pkg is None:
        abort(404, 'No package found')
    content = render_template('badge.svg', numrepos=pkg.num_repos)
    return Response(content, mimetype='image/svg+xml; charset=utf-8')


@app.route('/package/<pkgname>/', defaults={'page': 1})
@app.route('/package/<pkgname>/<int:page>')
def detail(pkgname, page):
    repos, pagination = get_pkg_repos(pkgname, page, PER_PAGE)
    if not repos and page != 1:
        abort(404)

    total = pagination.total_count
    results = [app.config.get('PKG_REPOS_HEADER_ROW')]
    for repo in repos:
        url = github_url(repo.url) if repo.url else ''
        results.append((repo.full_name, anchor(url, target='_blank')))

    return _render('detail', pkgname=pkgname, numrepos=total,
                   results=results, pagination=pagination)


@app.route('/result/<keywords>/', defaults={'page': 1})
@app.route('/result/<keywords>/<int:page>')
def result(keywords, page):
    keywords = unquote(keywords)
    packages, pagination = find_packages(keywords.split(), page, PER_PAGE)
    if not packages:
        if page == 1:
            flash('No packages found.', 'failed')
            return _render('index', keywords=keywords)
        else:
            abort(404)

    total = pagination.total_count
    page_title = app.config.get('INDEX_PAGE_TITLE')
    page_header = app.config.get('INDEX_PAGE_HEADER')
    results = [app.config.get('SEARCH_RESULT_HEADER_ROW')]

    for p in packages:
        if p.num_repos > 0:
            name = anchor(url_for('detail', pkgname=p.name), p.name)
        else:
            name = p.name
        results.append((name, p.num_repos, p.num_pyfiles,
                        p.num_reqfiles, p.str_updated(DATE_FORMAT)))

    return _render('result', total=total, title=page_title, header=page_header,
                   keywords=keywords, results=results, pagination=pagination)
