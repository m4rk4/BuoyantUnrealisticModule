import base64, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    return json.loads(el.string)


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    page_json = next_data['props']['pageProps']['data']

    item = {}
    item['id'] = page_json['id']
    item['url'] = page_json['contentUrl']
    item['title'] = page_json['headline']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromtimestamp(page_json['createdDate'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if page_json.get('lastModifiedDate'):
        dt_loc = datetime.fromtimestamp(page_json['lastModifiedDate'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    if page_json.get('author'):
        item['author'] = {
            "name": page_json['author']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    elif page_json.get('byline'):
        bylines = re.split(r'\sand\s|,\s', page_json['byline'], flags=re.I)
        if len(bylines) == 1:
            item['author'] = {
                "name": page_json['byline']
            }
            item['authors'] = []
            item['authors'].append(item['author'])
        else:
            if 'Nikkei' in bylines[-1]:
                del bylines[-1]
            item['authors'] = [{"name": x} for x in bylines]
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

    item['tags'] = []
    item['tags'].append(page_json['rootCategory']['name'])
    item['tags'].append(page_json['primaryTag']['name'])
    if page_json.get('additionalTags'):
        item['tags'] += [x['name'] for x in page_json['additionalTags']]

    if page_json.get('preview'):
        item['summary'] = BeautifulSoup(page_json['preview'], 'html.parser').get_text()

    item['content_html'] = ''
    if page_json.get('subhead'):
        item['content_html'] += '<p><em>' + page_json['subhead'] + '</em></p>'
        if 'summary' not in item:
            item['summary'] = page_json['subhead']

    if page_json.get('image'):
        item['image'] = page_json['image']['imageUrl']
        item['content_html'] += utils.add_image(page_json['image']['imageUrl'], page_json['image'].get('fullCaption'))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if page_json.get('body'):
        body = BeautifulSoup(page_json['body'], 'lxml')
    else:
        body_url = 'https://asia.nikkei.com/__service/v1/piano/article_access/' + base64.b64encode(urlsplit(url).path.encode()).decode()
        body_json = utils.get_url_json(body_url)
        if body_json:
            if save_debug:
                utils.write_file(body_json, './debug/content.json')
            body = BeautifulSoup(body_json['body'], 'html.parser')
        else:
            body = None

    if body:
        for el in body.find_all(class_='o-ads'):
            el.decompose()

        for el in body.find_all(id='AdAsia'):
            el.decompose()

        for el in body.find_all(class_='ez-embed-type-image'):
            new_html = ''
            if el.img:
                if el.img.get('full'):
                    img_src = el.img['full']
                else:
                    img_src = el.img['src']
                cap = el.find(class_='article__caption')
                if cap:
                    for it in cap.find_all('span', class_='ezstring-field'):
                        it.unwrap()
                    caption = cap.decode_contents().strip()
                else:
                    caption = ''
                new_html += utils.add_image(img_src, caption)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled ez-embed-type-image in ' + item['url'])

        item['content_html'] += body.div.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/rss/' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for article in next_data['props']['pageProps']['data']['stream']:
        if save_debug:
            logger.debug('getting content for ' + article['url'])
        item = get_content(article['url'], args, site_json, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['title'] = next_data['props']['pageProps']['data']['name'] + ' | Nikkei Asia'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
