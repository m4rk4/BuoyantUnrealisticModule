import json, pytz, re
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime
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
    next_url = split_url.scheme + '://' + split_url.netloc + '/_next/data/' + site_json['buildId'] + path + '.json' + params
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

    doc_info = next_data['pageProps']['docInfo']
    if next_data['pageProps']['seoConfig'].get('newsArticleJsonLD'):
        article_json = next_data['pageProps']['seoConfig']['newsArticleJsonLD']
    else:
        article_json = {}

    item = {}
    item['id'] = doc_info['post_id']
    if article_json.get('url'):
        item['url'] = article_json['url']
    else:
        item['url'] = url
    item['title'] = doc_info['title']

    if article_json.get('datePublished'):
        dt = datetime.fromisoformat(article_json['datePublished'])
    else:
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromtimestamp(doc_info['epoch'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('dateModified'):
        dt = datetime.fromisoformat(article_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    if doc_info.get('authors'):
        item['authors'] = [{"name": x} for x in doc_info['authors']]
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'].replace(',', '&#44;') for x in item['authors']])).replace('&#44;', ',')
		}
    elif article_json.get('author'):
        item['author'] = {
            "name": article_json['author']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    elif article_json.get('publisher'):
        item['author'] = {
            "name": article_json['publisher']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
    else:
        item['author'] = {
            "name": doc_info['source']
        }
        item['authors'] = []
        item['authors'].append(item['author'])


    item['tags'] = []
    if doc_info.get('city_name'):
        item['tags'].append(doc_info['city_name'])
    if doc_info.get('category_display'):
        item['tags'].append(doc_info['category_display'])
    if doc_info.get('unified_category'):
        item['tags'].append(doc_info['unified_category'])

    if doc_info.get('image'):
        item['_image'] = 'https://img.particlenews.com/img/id/' + doc_info['image']

    if doc_info.get('summary'):
        item['summary'] = doc_info['summary']
    elif doc_info.get('ai_summary'):
        item['summary'] = doc_info['ai_summary']
    elif article_json.get('description'):
        item['summary'] = article_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item
    
    soup = BeautifulSoup(doc_info['content'], 'html.parser')
    if soup.contents[0].name == 'body':
        soup.contents[0].unwrap()

    if soup.contents[0].name == 'div' and not soup.contents[0].get('class'):
        soup.contents[0].unwrap()

    if save_debug:
        utils.write_file(str(soup), './debug/debug.html')

    for el in soup.select('p:has(> a[href*=\"foxnews.onelink.me\"])'):
        el.decompose()

    for el in soup.select('div:has(> iframe[src*=\"nyp-video-player/embed\"])'):
        el.decompose()

    for el in soup.select('p:has(a[href*=\"people-true-crime-newsletter-sign-up\"])'):
        el.decompose()

    for el in soup.select('p:has(a)'):
        if el.get_text(strip=True).isupper():
            el.decompose()
        elif el.get_text(strip=True) == el.a.get_text(strip=True):
            el.decompose()

    for el in soup.select('div:not([class]):has(> iframe)'):
        el.unwrap()

    for el in soup.select('p:has(> img)'):
        if not el.get_text(strip=True):
            el.unwrap()

    for el in soup.contents:
        # print(type(el))
        new_html = ''
        if isinstance(el, NavigableString):
            continue
        if el.name == 'p' or el.name == 'ul':
            continue
        elif el.name == 'figure':
            if el.get('class') and 'wp-block-embed' in el['class']:
                if 'wp-block-embed-twitter' in el['class']:
                    links = el.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
            elif el.find('img'):
                img = el.find('img')
                if img.get('alt') and img['alt'].startswith('https'):
                    img_src = img['alt']
                else:
                    params = parse_qs(urlsplit(img['src']).query)
                    if 'url' in params:
                        img_src = 'https://img.particlenews.com/img/id/' + params['url'][0]
                    else:
                        img_src = img['src']
                caption = ''
                if el.name == 'figure':
                    it = el.find('figcaption')
                    if it:
                        if it.i:
                            x = it.i.find('p')
                            if x:
                                caption = x.decode_contents()
                                x.decompose()
                            if it.i.get_text(strip=True):
                                if caption:
                                    caption = ' | ' + caption
                                caption = it.i.decode_contents() + caption
                        else:
                            caption = it.decode_contents()
                new_html = utils.add_image(img_src, caption)
            elif el.find('iframe'):
                it = el.find('iframe')
                new_html += utils.add_embed(it['src'])
        elif el.name == 'img':
            if el.get('alt') and el['alt'].startswith('https'):
                img_src = el['alt']
            else:
                params = parse_qs(urlsplit(el['src']).query)
                if 'url' in params:
                    img_src = 'https://img.particlenews.com/img/id/' + params['url'][0]
                else:
                    img_src = el['src']
            new_html = utils.add_image(img_src)
        elif el.name == 'div' and not el.get('class'):
            if el.find('iframe'):
                new_html = utils.add_embed(el.iframe['src'])
            elif el.find('video'):
                it = el.find('source')
                if it:
                    new_html = utils.add_video(it['src'], it['type'], el.video.get('poster'), el.video.get('title'), use_videojs=True)
                elif el.video.get('src'):
                    new_html = utils.add_video(el.video['src'], 'video/mp4', '', '', use_videojs=True)
        elif el.name == 'iframe':
            new_html = utils.add_embed(el['src'])
        elif el.name == 'blockquote':
            if el.get('class'): 
                if 'twitter-tweet' in el['class']:
                    links = el.find_all('a')
                    new_html = utils.add_embed(links[-1]['href'])
                elif 'instagram-media' in el['class']:
                    new_html = utils.add_embed(el['data-instgrm-permalink'])
            else:
                new_html = utils.add_blockquote(el.decode_contents())
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled element {} in {}'.format(el.name, item['url']))

    item['content_html'] = str(soup)

    if doc_info.get('origin_url'):
        item['content_html'] += '<p><a href="' + doc_info['origin_url'] + '" target="_blank"><b>Read original article</b></a></p>'
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
