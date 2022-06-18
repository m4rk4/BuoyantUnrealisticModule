import json, re
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

from feedhandlers import fusion
import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(image_item, width_target):
    # Skip ad images
    if image_item['_id'] == '4K7PGY6HLZBTJGKNNZBXD3Z7XE' or image_item['_id'] == 'MLVRVZ6SGRHKJCNR4655R6VUCQ' or image_item['_id'] == 'YB4XJEM2RJAHVHQP5VTXZ43WIM':
        return None
    if image_item.get('credits'):
        if image_item['credits'].get('affiliation'):
            for it in image_item['credits']['affiliation']:
                if 'Fanatics' in it['name']:
                    return None
        if image_item['credits'].get('by'):
            for it in image_item['credits']['by']:
                if 'Fanatics' in it['name']:
                    return None

    images = []
    if image_item.get('width'):
        image = {}
        image['url'] = image_item['url']
        image['width'] = int(image_item['width'])
        images.append(image)
    if image_item.get('resized_urls'):
        for key, val in image_item['resized_urls'].items():
            m = re.search(r'\/resizer\/[^\/]+\/(\d+)x', val)
            if m:
                image = {}
                image['url'] = val
                image['width'] = int(m.group(1))
                images.append(image)
    image = utils.closest_dict(images, 'width', width_target)
    return image['url']


def get_item(content, url, args, save_debug):
    item = {}
    item['id'] = content['_id']
    item['url'] = url
    item['title'] = content['headlines']['basic']

    dt = datetime.fromisoformat(content['first_publish_date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(content['last_updated_date'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    # Check age
    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    authors = []
    for byline in content['credits']['by']:
        authors.append(byline['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if content['taxonomy'].get('seo_keywords'):
        item['tags'] = content['taxonomy']['seo_keywords'].copy()
    else:
        if content['taxonomy'].get('topics'):
            for tag in content['taxonomy']['topics']:
                if not tag['name'].startswith('@'):
                    item['tags'].append(tag['name'])
        if content['taxonomy'].get('tags'):
            for tag in content['taxonomy']['tags']:
                if not tag['text'].startswith('@'):
                    item['tags'].append(tag['text'])

    lead_image = None
    if content['promo_items']['basic']['type'] == 'image':
        lead_image = content['promo_items']['basic']
        item['_image'] = lead_image['url']

    item['summary'] = content['description']['basic']
    item['content_html'] = fusion.get_content_html(content, lead_image, resize_image, url, save_debug)
    return item


def get_content(url, args, save_debug=False, d=''):
    split_url = urlsplit(url)
    if not d:
        d = fusion.get_deployment_value(url)
        if d < 0:
            return None

    query = '{{"website_url":"{}"}}'.format(split_url.path)
    api_url = 'https://www.cleveland.com/pf/api/v3/content/fetch/content-api?query={}&d={}&_website=cleveland'.format(quote_plus(query), d)
    if save_debug:
        logger.debug('getting content from ' + api_url)

    content = utils.get_url_json(api_url)
    if not content:
        return None
    if save_debug:
        utils.write_file(content, './debug/debug.json')
    return get_item(content, url, args, save_debug)


def get_search_feed(args, save_debug=False):
    split_url = urlsplit(args['url'])
    d = fusion.get_deployment_value('https://www.cleveland.com')
    if d < 0:
        return None

    query = parse_qs(split_url.query)['q'][0]

    react_js = utils.get_url_html('https://www.cleveland.com/pf/dist/engine/react.js?d=' + d)
    for m in re.findall(r'function\(e\)\{e\.exports=JSON\.parse\(\'(\{.+?\})\'\)', react_js):
        m_js = json.loads(m.replace("\'", "\\'"))
        if m_js.get('querylyKey') and m_js['domain'] == 'cleveland.com':
            break

    queryly = utils.get_url_html('https://api.queryly.com/v4/search.aspx?queryly_key={}&initialized=1&&query={}&endindex=0&batchsize=20&callback=&extendeddatafields=&timezoneoffset=300&uiversion=1'.format(m_js['querylyKey'], query))
    m = re.search(r'results = JSON\.parse\(\'(.+?)\'\);\s', queryly)
    if not m:
        debugg.warning('no queryly results found for ' + args['url'])
        return None

    queryly_results = json.loads(m.group(1))
    n = 0
    items = []
    for result in queryly_results['items']:
        item = get_content(result['link'], args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed


def get_feed(args, save_debug=False):
    if '/search/' in args['url']:
        return get_search_feed(args, save_debug)

    split_url = urlsplit(args['url'])
    d = fusion.get_deployment_value('{}://{}'.format(split_url.scheme, split_url.netloc))
    if d < 0:
        return None

    if split_url.path.startswith('/staff/'):
        query = '{{"limit":10,"offset":0,"uri":"/staff/{0}/posts.html","id":"{0}","arc-site":"cleveland"}}'.format(split_url.path.split('/')[2])
        api_url = 'https://www.cleveland.com/pf/api/v3/content/fetch/author-feed-api?query={}&d={}&_website=cleveland'.format(quote_plus(query), d)
    else:
        query = '{{"limit":10,"offset":0,"section":"{}"}}'.format(split_url.path.split('/')[1])
        api_url = 'https://www.cleveland.com/pf/api/v3/content/fetch/section-feed-api?query={}&d={}&_website=cleveland'.format(quote_plus(query), d)

    if save_debug:
        logger.debug('getting feed from ' + api_url)
    section_feed = utils.get_url_json(api_url)
    if not section_feed:
        return None
    if save_debug:
        utils.write_file(section_feed, './debug/feed.json')

    n = 0
    items = []
    for content in section_feed:
        # Check age
        if args.get('age'):
            item = {}
            dt = datetime.fromisoformat(content['first_publish_date'].replace('Z', '+00:00'))
            item['_timestamp'] = dt.timestamp()
            if not utils.check_age(item, args):
                continue
        url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, content['canonical_url'])
        if save_debug:
            logger.debug('getting content from ' + url)
            if content['_id'] == 'URN6T4ADLRAF7KG364WIEJUZMA':
                utils.write_file(content, './debug/debug.json')
        item = get_item(content, url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed
