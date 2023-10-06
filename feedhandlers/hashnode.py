import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    return '{}://{}{}??w={}&auto=compress,format&format=webp'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/next.json')

    post_json = json.loads(next_data['pageProps']['post'])
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['_id']
    item['url'] = next_data['pageProps']['rootLayout']['seoSchema']['url']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['dateAdded'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = post_json['author']['name']

    if post_json.get('tags'):
        logger.warning('unhandled tags in ' + item['url'])

    if post_json.get('brief'):
        item['summary'] = post_json['brief']

    item['content_html'] = ''
    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subtitle'])

    if post_json.get('coverImage'):
        item['_image'] = post_json['coverImage']
        item['content_html'] += utils.add_image(resize_image(item['_image']))

    if post_json.get('audioUrls'):
        if post_json['audioUrls'].get('male'):
            item['_audio'] = post_json['audioUrls']['male']
        elif post_json['audioUrls'].get('female'):
            item['_audio'] = post_json['audioUrls']['female']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen to article</a></span></div>'.format(item['_audio'], config.server)

    soup = BeautifulSoup(post_json['content'], 'html.parser')
    for el in soup.find_all('img', attrs={"alt": True}):
        if el.parent and el.parent.name == 'p':
            el_parent = el.parent
        else:
            el_parent = el
        # There seems to be no standard for captions
        # Caption: https://michaellin.hashnode.dev/how-to-be-a-10x-software-engineer
        caption = el_parent.get_text().strip()
        if not caption:
            for it in el_parent.find_next_siblings():
                if it.name == 'None':
                    continue
                elif it.name == 'table':
                    # Caption in next table: https://michaellin.hashnode.dev/why-i-quit-a-450000-engineering-job-at-netflix
                    caption = it.get_text().strip()
                    it.decompose()
                elif it.name == 'p':
                    # Captions in next paragraph: https://michaellin.hashnode.dev/how-to-quit-your-tech-job-the-right-way
                    caption = it.get_text().strip()
                    if it.em and it.em.get_text().strip() == caption:
                        it.decompose()
                    elif re.search(r'^Caption', caption):
                        it.decompose()
                    else:
                        caption = ''
                break
        new_html = utils.add_image(el['src'], caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el_parent.insert_after(new_el)
        el_parent.decompose()

    for el in soup.find_all(class_='embed-wrapper'):
        it = el.find(class_='embed-card')
        if it:
            new_html = utils.add_embed(it['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embed-wrapper in ' + item['url'])

    for el in soup.find_all('pre'):
        el['style'] = 'margin-left:2vw; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'

    for el in soup.find_all('code'):
        if not (el.parent and el.parent == 'p'):
            el['style'] = 'background:#F2F2F2;'

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
