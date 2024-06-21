import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

