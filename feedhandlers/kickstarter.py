import html, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # For video widgets
    # view-source:https://www.kickstarter.com/projects/steamforged/monster-hunter-world-iceborne-board-game/widget/video.html
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if not re.search(r'/widget/video\.html', url):
        logger.warning('unhandled url ' + url)
        return None
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    m = re.search(r'window\.current_project\s?=\s?"({.*?})";\n', page_html)
    if not m:
        logger.warning('unable to parse current_project data in ' + url)
        return None
    project_json = json.loads(m.group(1).replace('&quot;', '"'))
    if save_debug:
        utils.write_file(project_json, './debug/debug.json')

    item = {}
    item['id'] = project_json['id']
    item['url'] = project_json['urls']['web']['project']
    item['title'] = project_json['name']
    item['author'] = {"name": project_json['creator']['name']}
    item['summary'] = project_json['blurb']
    item['_image'] = project_json['video']['frame']
    item['content_html'] = utils.add_video(project_json['video']['high'], 'video/mp4', project_json['video']['frame'], item['title'])
    return item