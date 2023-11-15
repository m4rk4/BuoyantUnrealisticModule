import json, re
import dateutil.parser
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    clean_url = utils.clean_url(url)
    if clean_url.endswith('/'):
        clean_url = clean_url[:-1]

    #content_json = utils.get_url_json(clean_url + '.lazy-fetch.json')
    data_json = utils.get_url_json(clean_url + '.json')
    if not data_json:
        return None
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    content_html = utils.get_url_html(clean_url + '.lazy-fetch-html-content.html')
    if save_debug:
        utils.write_file(content_html, './debug/debug.html')
    soup = BeautifulSoup(content_html, 'html.parser')

    item = {}
    item['id'] = data_json['jcr:uuid']
    item['url'] = clean_url
    item['title'] = data_json['sni:seoTitle']

    dt = dateutil.parser.parse(data_json['sni:origPubDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = dateutil.parser.parse(data_json['cq:lastModified']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for el in soup.find_all(class_='o-Attribution__a-Name'):
        authors.append(el.get_text().strip())
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for el in soup.find_all('a', class_='a-Tag'):
        item['tags'].append(el.get_text().strip())
    if not item.get('tags'):
        del item['tags']

    body = soup.find(class_='article-body')
    if body:
        for el in body.find_all(text=lambda text: isinstance(text, Comment)):
            el.extract()

        for el in body.find_all('section', class_='o-CustomRTE'):
            el.unwrap()

        for el in body.find_all('section', class_=['o-EditorialPromo', 'o-JukeBox']):
            el.decompose()

        for el in body.find_all('link', attrs={"type": "text/css"}):
            el.decompose()

        for el in body.find_all(class_='o-ImageEmbed'):
            img = el.find('img')
            if img:
                img_src = img['src'].split('.rend')[0]
                new_html = utils.add_image(img_src)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled o-ImageEmbed in ' + item['url'])

        item['content_html'] = body.decode_contents()

    return item