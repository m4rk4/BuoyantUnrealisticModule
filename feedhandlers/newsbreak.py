import json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
    if len(paths) == 2:
        params = '?local_id=' + paths[0] + '&doc_id=' + paths[1]
    else:
        params = ''
    next_url = '{}://{}/_next/data/{}{}.json{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, params)
    print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
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

    if next_data['pageProps'].get('__N_REDIRECT'):
        logger.debug('getting content from ' + next_data['pageProps']['__N_REDIRECT'])
        return utils.get_content(next_data['pageProps']['__N_REDIRECT'], {}, False)

    page_json = next_data['pageProps']
    item = {}
    item['id'] = page_json['id']
    item['url'] = page_json['seoCanonicalUrl']
    item['title'] = page_json['title']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = dateutil.parser.parse(page_json['date'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if page_json['seoConfig'].get('articleJson') and page_json['seoConfig']['articleJson'].get('dateModified'):
        dt_loc = dateutil.parser.parse(page_json['seoConfig']['articleJson']['dateModified'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    if page_json.get('authors'):
        authors = []
        for it in page_json['authors']:
            authors.append(it.replace(',', '&#44;'))
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)).replace('&#44;', ',')
    elif page_json.get('publisher'):
        item['author'] = {"name": page_json['publisher']}

    item['tags'] = []
    if page_json.get('cityChannel'):
        item['tags'].append(page_json['cityChannel']['name'])
    if page_json.get('catChannel'):
        if page_json['catChannel']['name'] not in item['tags']:
            item['tags'].append(page_json['catChannel']['name'])

    if page_json.get('cover'):
        item['_image'] = 'https://img.particlenews.com/image.php?url=' + page_json['cover']

    if page_json['contentType'] == 'VIDEO':
        item['content_html'] = utils.add_video(page_json['videoUrl'], 'video/mp4', item['_image'], item['title'], use_videojs=True)
    elif page_json.get('content'):
        soup = BeautifulSoup(page_json['content'], 'html.parser')
        soup.div.unwrap()

        for el in soup.find_all('nbtemplate'):
            el.decompose()

        for el in soup.find_all('a', class_='promo-link__link'):
            el.decompose()

        for el in soup.find_all('iframe'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            for it in el.find_parents(['div', 'p']):
                it.unwrap()
            it = el.find_previous_sibling()
            if (it.name == 'figure' or it.name == 'p') and it.img:
                if page_json['cover'] in it.img['src']:
                    it.decompose()
            el.replace_with(new_el)

        for el in soup.find_all('figure'):
            if el.img:
                if 'img.particlenews.com' in el.img['src']:
                    params = parse_qs(urlsplit(el.img['src']).query)
                    img_src =  'https://img.particlenews.com/image.php?url=' + params['url'][0]
                else:
                    img_src = el.img['src']
                if el.figcaption:
                    caption = el.figcaption.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_image(img_src, caption)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled figure in ' + item['url'])

        for el in soup.select('p:has(> img)'):
            if el.img:
                if 'img.particlenews.com' in el.img['src']:
                    params = parse_qs(urlsplit(el.img['src']).query)
                    img_src =  'https://img.particlenews.com/image.php?url=' + params['url'][0]
                else:
                    img_src = el.img['src']
                new_html = utils.add_image(img_src)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled p > img in ' + item['url'])

        item['content_html'] = str(soup)
    elif page_json['originalUrl'] != item['url']:
        logger.debug('getting content form ' + page_json['originalUrl'])
        orig_item = utils.get_content(page_json['originalUrl'], {}, False)
        if orig_item:
            item['content_html'] = orig_item['content_html']
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    items = []
    for article in next_data['pageProps']['feed']['list']:
        if 'publisherChannel' in article:
            article_url = 'https://www.newsbreak.com/{}/{}'.format(article['publisherChannel']['id'], article['hashedId'])
        else:
            article_url = 'https://www.newsbreak.com/{}/{}'.format(re.sub(r'\s|\.', '-', article['publisher']), article['hashedId'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
