import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', attrs={"type": "application/ld+json"})
    if not el:
        logger.warning('unable to find ld+json in ' + url)
        return None
    ld_json = json.loads(el.string.replace('\n', '').replace('\r', ''))
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    el = page_soup.find('meta', attrs={"name": "cXenseParse:articleid"})
    item['id'] = el['content']

    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    if ld_json.get('author'):
        if isinstance(ld_json['author'], str):
            item['author'] = {"name": ld_json['author']}
        elif isinstance(ld_json['author'], dict):
            item['author'] = {"name": ld_json['author']['name']}
        elif isinstance(ld_json['author'], list):
            authors = []
            for it in ld_json['author']:
                authors.append(it['name'])
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        el = page_soup.select('div.byline > span.credit')
        if el:
            item['author']['name'] += ' ({})'.format(el[0].get_text().strip())
    elif ld_json['publisher']:
        item['author'] = {"name": ld_json['publisher']['name']}

    if ld_json.get('keywords'):
        item['tags'] = [it.strip() for it in ld_json['keywords'].split(',')]

    if ld_json.get('image'):
        item['_image'] = ld_json['image']['url']
    elif ld_json.get('thumbnailUrl'):
        item['_image'] = ld_json['thumbnailUrl']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    data = '748959383367:{}:'.format(item['id'])
    data = base64.urlsafe_b64encode(base64.urlsafe_b64encode(data.encode()))
    content_url = 'https://www.japantimes.co.jp/ajax/getArticleContent/?data={}&is_old_article=0'.format(quote_plus(data))
    content_json = utils.get_url_json(content_url)
    if not content_json:
        logger.warning('unable to get article content from ' + content_url)
        return item
    if save_debug:
        utils.write_file(content_json, './debug/content.json')

    item['content_html'] = ''
    el = page_soup.select('div.jt-article-details > div.article-image-gallery')
    if el:
        it = el[0].find('a', class_='fresco')
        item['content_html'] += utils.add_image(it['href'], it.get('data-fresco-caption'))

    soup = BeautifulSoup(content_json['articleBody'], 'html.parser')
    body = soup.find(class_='article-body')
    for el in body.find_all(class_='jt_content_ad'):
        el.decompose()

    for el in body.find_all(class_='image_body'):
        new_html = ''
        for it in el.find_all('a', class_='fresco'):
            new_html += utils.add_image(it['href'], it.get('data-fresco-caption'))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled image_body in ' + item['url'])

    item['content_html'] += body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
