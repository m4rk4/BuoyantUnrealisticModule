import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if re.search('whitepapers\.theretister\.com', url):
        logger.warning('unsupported url ' + url)
        return None

    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if not el:
        logger.warning('unable to find ld+json in ' + url)
        return None

    ld_json = json.loads(el.string)
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = ld_json['mainEntityOfPage']['@id']
    item['url'] = ld_json['mainEntityOfPage']['@id']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": ld_json['author']['name']}

    item['tags'] = []
    for el in soup.find_all(class_='keyword_group'):
        if 'similar_topics' in el['class']:
            for it in el.find_all(class_='keyword_name'):
                tag = it.get_text().strip()
                if tag not in item['tags']:
                    item['tags'].append(tag)
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    for el in soup.select('div.header_right > h2'):
        item['content_html'] += '<p><em>{}</em></p>'.format(el.get_text())

    if ld_json.get('image'):
        item['_image'] = ld_json['image']['url']
        if not soup.find('a', href=item['_image']):
            item['content_html'] += utils.add_image(item['_image'])

    content = soup.find('div', id='body')
    if content:
        for el in content.find_all(class_=re.compile(r'adun|listinks|promo_article|wptl')):
            el.decompose()
        for el in content.find_all('script'):
            el.decompose()
        for el in content.find_all(attrs={"data-tf-widget": True}):
            el.decompose()

        for el in content.find_all(class_='CaptionedImage'):
            it = el.find('p')
            if it:
                caption = re.sub(r' - Click to enlarge', '', it.decode_contents(), flags=re.I)
            else:
                caption = ''
            it = el.find('img')
            if it:
                if it.parent.name == 'a':
                    new_html = utils.add_image(it.parent['href'], caption)
                else:
                    new_html = utils.add_image(it['src'], caption)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled CaptionedImage in ' + item['url'])

        for el in content.find_all(class_=['blockextract', 'boxout', 'sidebar']):
            new_html = utils.add_blockquote(el.decode_contents(), False)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in content.find_all('blockquote', class_='pullquote'):
            if el.p:
                new_html = utils.add_pullquote(el.p.decode_contents())
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled pullquote in ' + item['url'])

        for el in content.find_all('span', class_='label'):
            del el['class']
            el['style'] = 'color:#D60000; text-transform:uppercase; font-weight:bold;'

        item['content_html'] += content.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
