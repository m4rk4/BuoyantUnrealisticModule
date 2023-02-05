import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    clean_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
    page_html = utils.get_url_html(clean_url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', attrs={"type": "application/json", "sveltekit:data-url": split_url.path + '.json'})
    if not el:
        logger.warning('unable to find sveltekit:data in ' + clean_url)
        return None
    data_json = json.loads(el.string)
    body_json = json.loads(data_json['body'])
    if save_debug:
        utils.write_file(body_json, './debug/debug.json')
    link_data = body_json['linkData']

    item = utils.get_content(link_data['url'], args, save_debug)
    if item:
        return item

    item = {}
    item['id'] = link_data['id']
    item['url'] = link_data['url']
    item['title'] = link_data['title']

    dt = datetime.fromtimestamp(link_data['publishedTimestamp']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    if link_data.get('author'):
        item['author']['name'] = '{} ({})'.format(link_data['author']['name'], link_data['site']['name'])
    else:
        item['author']['name'] = link_data['site']['name']

    if link_data.get('thumbnail'):
        item['_image'] = link_data['thumbnail']['url']

    try:
        article_json = json.loads(body_json['fullArticle'].encode('latin1').decode().strip())
        if save_debug:
            utils.write_file(article_json, './debug/article.json')
        soup = BeautifulSoup(article_json['content'], 'html.parser')
    except json.decoder.JSONDecodeError:
        soup = BeautifulSoup(body_json['fullArticle'].encode('latin1').decode().strip(), 'html.parser')

    el = soup.find()
    if el.name == 'div':
        el.unwrap()
    #elif el.name == 'html'

    for el in soup.find_all(class_='text'):
        el.unwrap()

    for el in soup.find_all('figure'):
        new_html = ''
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
        else:
            it = el.find('figcaption')
            if it:
                caption = it.decode_contents()
            else:
                caption = ''
            it = el.find('img')
            if it:
                new_html = utils.add_image(it['src'], caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled figure in ' + clean_url)

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el
        while it.parent and it.parent.name == 'div':
            it = it.parent
        it.insert_after(new_el)
        it.decompose()

    for el in soup.find_all(class_='related-entries'):
        el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    item['content_html'] = ''
    el = soup.find()
    if el.name == 'p' and item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'])
    item['content_html'] += str(soup)
    return item