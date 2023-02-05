import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote

import utils
from feedhandlers import drupal, rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    m = re.search(r'/ubernode/(\d+)', page_html)
    if not m:
        logger.warning('unable to find ubernode id in ' + url)
        return None
    ubernode = utils.get_url_json('https://www.nasa.gov/api/2/ubernode/' + m.group(1))
    if not ubernode:
        return None
    return get_item(ubernode, args, site_json, save_debug)


def get_item(ubernode, args, site_json, save_debug):
    if save_debug:
        utils.write_file(ubernode, './debug/debug.json')

    item = {}
    item['id'] = ubernode['_source']['nid']
    item['url'] = 'https://www.nasa.gov' + ubernode['_source']['uri']
    item['title'] = ubernode['_source']['title']

    dt = datetime.fromisoformat(ubernode['_source']['promo-date-time'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": ubernode['_source']['name']}

    tags = []
    item['tags'] = []
    if ubernode['_source'].get('primary-tag'):
        tags.append(ubernode['_source']['primary-tag'])
    if ubernode['_source'].get('secondary-tag'):
        tags.append(ubernode['_source']['secondary-tag'])
    if ubernode['_source'].get('topics'):
        tags += ubernode['_source']['topics']
    if ubernode['_source'].get('missions'):
        tags += ubernode['_source']['missions']
    tags = list(set(tags))
    for it in tags:
        term = utils.get_url_json('https://www.nasa.gov/api/2/term/{}'.format(it))
        if term:
            item['tags'].append(term['_source']['name'])

    if ubernode['_source'].get('master-image'):
        item['_image'] = ubernode['_source']['master-image']['uri'].replace('public://', 'https://www.nasa.gov/sites/default/files/styles/full_width_feature/public/')

    if ubernode['_source'].get('pr-leader-sentence'):
        item['summary'] = ubernode['_source']['pr-leader-sentence']

    item['content_html'] = ubernode['_source']['body']
    if ubernode['_source'].get('credits'):
        item['content_html'] += ubernode['_source']['credits']
    soup = BeautifulSoup(item['content_html'], 'html.parser')
    for el in soup.find_all(class_='dnd-atom-wrapper'):
        new_html = ''
        if 'type-image' in el['class']:
            it = el.find(class_='caption')
            if it:
                caption = it.decode_contents()
            else:
                caption = ''
            img_src = 'https://www.nasa.gov' + el.img['src']
            new_html = utils.add_image(img_src, caption)
        elif 'type-video' in el['class']:
            if el.find(class_='scald-youtube-wrapper'):
                new_html = utils.add_embed(el.iframe['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled dnd-atom-wrapper in ' + item['url'])

    item['content_html'] = ''
    if ubernode['_source']['ubernode-type'] == 'image':
        item['content_html'] += utils.add_image(item['_image'], ubernode['_source'].get('image-feature-caption'))
    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://blogs.nasa.gov/webb/feed/
    if '/feed/' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    page_html = utils.get_url_html(args['url'])
    m = re.search(r'window\.cardFeed = (.+);\s*\n', page_html)
    if not m:
        logger.warning('unable to parse cardFeed data in ' + args['url'])
        return None
    card_json = json.loads(re.sub(r',]$', ']', m.group(1)))
    utils.write_file(card_json, './debug/debug.json')
    card_feed = next((it for it in card_json if it['type'] == 'card_feed'), None)
    if not card_feed:
        card_feed = next((it for it in card_json if it['type'] == 'listing'), None)
    if not card_feed:
        logger.warning('unknown card feed in ' + args['url'])

    q = '((ubernode-type:feature OR ubernode-type:image OR ubernode-type:press_release OR ubernode-type:collection_asset OR ubernode-type:mediacast) AND '
    if card_feed.get('routes'):
        q += '(routes:{}))'.format(card_feed['routes'][0])
    elif card_feed.get('collections'):
        q += '(collections:{}))'.format(card_feed['collections'][0])
    elif card_feed.get('topics'):
        q += '(topics:{}))'.format(card_feed['topics'][0])
    elif card_feed.get('missions'):
        q += '(missions:{}))'.format(card_feed['missions'][0])
    else:
        logger.warning('unhandled card feed in ' + args['url'])
        return None

    feed_url = 'https://www.nasa.gov/api/2/ubernode/_search?size=10&from=0&sort=promo-date-time%3Adesc&q=' + q.replace(' ', '%20')
    feed_json = utils.get_url_json(feed_url)
    if not feed_json:
        return None
    if save_debug:
        utils.write_file(feed_json, './debug/feed.json')

    n = 0
    feed_items = []
    for ubernode in feed_json['hits']['hits']:
        if save_debug:
            logger.debug('getting content for ' + 'https://www.nasa.gov' + ubernode['_source']['uri'])
        item = get_item(ubernode, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    m = re.search(r'<title>(.*)</title>', page_html)
    if m:
        feed['title'] = m.group(1)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed