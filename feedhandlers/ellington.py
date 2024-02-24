import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    story_id = ''
    m = re.search(r'news-story-(\d+)', page_html)
    if m:
        story_id = m.group(1)
    else:
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('meta', attrs={"itemprop": "identifier"})
        if el:
            story_id = el['content']
        else:
            el = soup.find('body')
            if el and el.get('id'):
                m = re.search(r'story_(\d+)', el['id'])
                if m:
                    story_id = m.group(1)
    if not story_id:
        logger.warning('unknown story id for ' + url)
        return None

    # https://help.ellingtoncms.com/m/98091/l/1279012-using-the-api
    split_url = urlsplit(url)
    api_url = 'https://{}/api/news/story/{}/'.format(split_url.netloc, story_id)
    story_json = utils.get_url_json(api_url)
    if not story_json:
        return None
    return get_item(story_json, args, site_json, save_debug)


def get_item(story_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item['id'] = story_json['id']
    item['url'] = story_json['share_url']
    item['title'] = story_json['headline']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromisoformat(story_json['pub_date'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_json.get('edited_at'):
        dt_loc = datetime.fromisoformat(story_json['updated'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in story_json['bylines']:
        authors.append(it['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if story_json.get('tease'):
        item['summary'] = story_json['tease']

    item['content_html'] = ''
    if story_json.get('subhead'):
        item['content_html'] += '<p><em>' + story_json['subhead'] + '</em></p>'

    if story_json.get('thumbnails'):
        item['_image'] = story_json['thumbnails']['original']
        captions = []
        if story_json.get('photo_caption'):
            captions.append(story_json['photo_caption'])
        if story_json.get('photo_credit'):
            captions.append(story_json['photo_credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    for it in story_json['story'].strip().split('\n'):
        text = re.sub(r'https?://[^\s]+', r'<a href=\"\g<0>\">\g<0></a>', it)
        if re.search(r'^[^a-z]*(:|$)', re.sub(r'Mc([A-Z])', r'MC\1', it)):
            item['content_html'] += '<p><b>' + text + '</b></p>'
        else:
            item['content_html'] += '<p>' + text + '</p>'

    # TODO: links, styling, lists not formatted

    if story_json.get('inlines'):
        # TODO: https://www.timesfreepress.com/news/2024/feb/20/basf-seeks-the-right-chemistry-chemical-giant/
        logger.warning('unhandled inlines in ' + item['url'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # TODO: section feeds
    split_url = urlsplit(url)
    api_url = 'https://{}/api/news/story/?limit=10&offset=0'.format(split_url.netloc)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    n = 0
    feed_items = []
    for story in api_json['results']:
        if save_debug:
            logger.debug('getting content for ' + story['share_url'])
        item = get_item(story, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
