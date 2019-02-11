# -*- coding: utf-8 -*-

# Maximum Levenshtein edit distance used for approximate matching
MAX_EDIT_DISTANCE = 3

# Index page
INDEX_PAGE_TITLE = 'countpy'
INDEX_PAGE_HEADER = 'Search | countpy'

# About page
ABOUT_PAGE_TITLE = 'About countpy'
ABOUT_PAGE_HEADER = 'About'

# Contact page
CONTACT_PAGE_TITLE = 'Contact Us'
CONTACT_PAGE_HEADER = 'Contact Us'

# GitHub link to project
GITHUB_URL = 'https://github.com/soodoku/countpy'

# Header row for displaying search result table
SEARCH_RESULT_HEADER_ROW = (
    'package', 'number of repositories importing', 'number of files',
    'number of requirements files', 'date'
)

# Header row for displaying repositories table of package
PKG_REPOS_HEADER_ROW = ('repo:name', 'repo:url')

# Number of items per page applied for table with pagination
PER_PAGE = 20

# When enabled, the number displayed in badge will be shortened, in which
# instead of '1500', it will become '1.5K' as example
SHORTEN_NUMBER_IN_BADGE = False

# Interval for manually saving (snapshot) database onto disk
REDIS_SAVE_INTERVAL = 300  # 5 mins
