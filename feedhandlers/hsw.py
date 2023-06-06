import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    m = re.search(r'<meta name="template" content="Quiz"', page_html, flags=re.I)
    if m:
        logger.debug('skipping quiz content in ' + url)
        return None
    m = re.search(r'content-(\d+)', page_html)
    if not m:
        logger.warning('unable to determine article content id in ' + url)
        return None

    split_url = urlsplit(url)
    content_json = utils.get_url_json('{}://{}/continuous/{}'.format(split_url.scheme, split_url.netloc, m.group(1)))
    if not content_json:
        return None
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['href']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['publish_date']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content_json['last_modified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in content_json['authors']:
        if it.get('middle_name'):
            authors.append('{} {} {}'.format(it['first_name'], it['middle_name'], it['last_name'].replace(',', '&#44;')))
        else:
            authors.append('{} {}'.format(it['first_name'], it['last_name'].replace(',', '&#44;')))
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)).replace('&#44;', ',')

    item['tags'] = []
    for it in content_json['taxonomy']:
        item['tags'].append(it['title'])
    if not item.get('tags'):
        del item['tags']

    if content_json.get('hero_image'):
        item['_image'] = content_json['hero_image']

    if content_json.get('description'):
        item['summary'] = content_json['description']

    soup = BeautifulSoup(content_json['body_html'], 'html.parser')
    for el in soup.find_all(class_='page-content'):
        it = el.find(class_='page-body')
        if it:
            it.unwrap()
        el.unwrap()

    for el in soup.find_all('div', class_=['clear-both', 'list', 'print:block', 'toc', 'w-full']):
        el.unwrap()

    for el in soup.find_all('div', attrs={"x-data": True}):
        el.unwrap()

    for el in soup.find_all(class_='ad-container'):
        el.decompose()

    for el in soup.find_all('a'):
        if el.get('name') and re.search(r'pt\d+', el['name']):
            el.decompose()
        elif el.get('class'):
            del el['class']

    for el in soup.find_all('span', attrs={"role": "button"}):
        it = el.find('svg')
        if it:
            it.decompose()
        el.unwrap()

    for el in soup.find_all(['h2', 'h3', 'h4'], attrs={"data-page-url": True}):
        el.attrs = {}

    for el in soup.find_all(class_='fragment-media'):
        new_html = ''
        img = el.find('img')
        if img:
            captions = []
            it = el.find(class_='media-sub')
            if it:
                captions.append(it.get_text().strip())
                it.decompose()
            it = el.find('figcaption')
            if it:
                captions.insert(0, it.get_text().strip())
            if img.get('data-src'):
                new_html = utils.add_image(img['data-src'], ' | '.join(captions))
            else:
                new_html = utils.add_image(img['src'], ' | '.join(captions))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.get('class') and 'editorial-sidebar' in el.parent['class']:
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled fragment-media in ' + item['url'])

    for el in soup.find_all('iframe'):
        if el.get('data-src'):
            new_html = utils.add_embed(el['data-src'])
        else:
            new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'div':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='blockquote'):
        it = el.find(class_=re.compile(r'px-\d'))
        if it:
            new_html = utils.add_blockquote(it.decode_contents())
        else:
            new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='sidebar-section'):
        new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_=re.compile(r'font-|text-')):
        del el['class']

    item['content_html'] = str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
