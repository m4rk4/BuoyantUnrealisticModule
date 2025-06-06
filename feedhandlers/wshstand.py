import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        params = ''
    else:
        params = '?id=' + paths[-1]
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
    next_url = '{}://{}/_next/data/{}{}.json{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, params)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    page_json = next_data['pageProps']

    item = {}
    item['id'] = page_json['ITEM_CODE']
    item['url'] = page_json['CANONICAL_URL']
    item['title'] = page_json['ITEM_DESC']

    # TODO: confirm timezone
    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromisoformat(page_json['TIMEGENERATED'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, date_only=True)

    item['authors'] = [{"name": x['AUTHOR_NAME']} for x in page_json['authorsArray']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = page_json['TAG_LIST'].split(',')
    item['summary'] = page_json['SUMMARY_TEXT']

    item['content_html'] = ''
    if page_json.get('SCREENCAP_IMAGE'):
        item['image'] = page_json['SCREENCAP_IMAGE']
        item['content_html'] += utils.add_image(page_json['SCREENCAP_IMAGE'])

    if page_json['TYPE_DESC'] == 'Podcast':
        item['content_html'] += '<div>&nbsp;</div>' + utils.add_audio(page_json['audioDetails']['DOWNLOAD_URL'], page_json['SCREENCAP_IMAGE'], item['title'], item['url'], page_json['SERIES_NAME'], 'https://washingtonstand.com/podcast/' +  page_json['SERIES_NAME'].lower(), utils.format_display_date(dt, date_only=True), int(page_json['audioDetails']['FILE_LENGTH']))

    if page_json.get('FULL_TEXT'):
        item['content_html'] += page_json['FULL_TEXT']
        item['content_html'] = item['content_html'].replace('<blockquote>', '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">')
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    articles = []
    if 'all' in paths:
        articles = next_data['pageProps']['publications']
        feed_title = 'News & Commentary | The Washington Stand'
    elif 'writers' in paths:
        articles = next_data['pageProps']['authorPublications']
        feed_title = next_data['pageProps']['AUTHOR_NAME'] + ' | The Washington Stand'
    elif 'topic' in paths:
        articles.append(next_data['pageProps']['firstPublication'])
        articles += next_data['pageProps']['publicationList']
        feed_title = next_data['pageProps']['topicTexts']['documentTitle'] + ' | The Washington Stand'
    elif len(paths) == 0:
        articles.append(next_data['pageProps']['leadStory'])
        articles.append(next_data['pageProps']['topPodcast'])
        articles += next_data['pageProps']['pastPublications']
        articles += next_data['pageProps']['topStories']
        articles += next_data['pageProps']['trending']
        feed_title = 'The Washington Stand'
    else:
        logger.warning('unhandled feed url ' + url)
        return None

    n = 0
    feed_items = []
    for article in articles:
        if 'CANONICAL_URL' in article:
            article_url = article['CANONICAL_URL']
        else:
            article_url = 'https://washingtonstand.com/{}/{}'.format(article['TYPE_DESC'].lower(), article['URL_SLUG'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
