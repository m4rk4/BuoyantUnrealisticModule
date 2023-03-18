import re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, images, width=900):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    img_id = paths[-1].split('-')[0]
    image = None
    for img in images:
        if img_id in img['url']:
            image = img
            break
    if not image:
        return img_src
    if image['width'] <= width:
        return image['url']
    return image['urlTemplate'].replace('{spec}', '{}wi'.format(width))


def get_content(url, args, site_json, save_debug=False):
    # https://www.typepad.com/services/apidocs
    tld = tldextract.extract(url)
    if tld.domain == 'typepad' or tld.domain == 'blogs':
        blogid = site_json['blogids'][tld.subdomain]
    else:
        blogid = site_json['blogid']

    m = re.search(r'/(\d{4})/(\d{2})/([^\.]+)\.html', url)
    if not m:
        logger.warning('unhandled url ' + url)
        return None

    api_url = 'https://api.typepad.com/blogs/{}/post-assets/@by-filename/{}:{}:{}.json'.format(blogid, m.group(1), m.group(2), m.group(3))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    post_json = api_json['entries'][0]
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['permalinkUrl']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['published'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = post_json['author']['displayName']

    if post_json.get('categories'):
        item['tags'] = post_json['categories'].copy()

    if post_json.get('embeddedImageLinks'):
        item['_image'] = post_json['embeddedImageLinks'][0]['url']

    if post_json.get('exerpt'):
        item['_image'] = post_json['exerpt']

    content = post_json['content']
    page_html = utils.get_url_html(url)
    if page_html:
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find(class_='entry-more')
        if el:
            content += el.decode_contents()

    soup = BeautifulSoup(content, 'html.parser')
    for el in soup.find_all(class_='asset-img-link'):
        it = el.find('img')
        if it:
            new_html = utils.add_image(resize_image(it['src'], post_json['embeddedImageLinks']))
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'p':
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled asset-img-link in ' + item['url'])

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('blockquote'):
        new_html = ''
        it = el.find('div', attrs={"align": "right"})
        if it:
            author = it.get_text()
            if author.startswith('—'):
                author = author[1:]
            it.decompose()
            new_html = utils.add_pullquote(el.get_text(), author)
        else:
            new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    item['content_html'] = str(soup)
    return item

def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
