import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_image(image_wrapper):
    it = image_wrapper.find('img')
    if it.get('original'):
        img_src = it['original']
    else:
        img_src = it['src']
    captions = []
    it = image_wrapper.find(class_='article-main-image-caption')
    if it and it.get_text().strip():
        if it.p:
            captions.append(it.p.decode_contents())
        else:
            captions.append(it.get_text().strip())
    it = image_wrapper.find(class_='article-main-image-credit')
    if it and it.get_text().strip():
        if it.p:
            captions.append(it.p.decode_contents())
        else:
            captions.append(it.get_text().strip())
    return utils.add_image(img_src, ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    if '/aaaggregated/' in url:
        redirect_url = utils.get_redirect_url(url)
        logger.warning('redirect url ' + redirect_url)
        item = utils.get_content(redirect_url, args, save_debug)
        return item

    page_html = utils.get_url_html(url, user_agent=site_json.get('user_agent'))
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', attrs={"data-drupal-selector": "drupal-settings-json"})
    if not el:
        logger.warning('unable to find drupal-settings-json in ' + url)
        return None

    data_json = json.loads(el.string)
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    content_json = data_json['crain_object']['content']

    item = {}
    item['id'] = content_json['NodeID']
    item['url'] = url
    item['title'] = content_json['Title']

    el = soup.find('meta', attrs={"property": "article:published_time"})
    if el:
        dt = datetime.fromisoformat(el['content']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    el = soup.find('meta', attrs={"property": "article:modified_time"})
    if el:
        dt = datetime.fromisoformat(el['content']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in content_json['Author']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for it in content_json['Topics']:
        item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']

    el = soup.find('meta', attrs={"name": "description"})
    if el:
        item['summary'] = el['content']

    content_html = ''
    el = soup.find(class_='article-main-image-wrapper')
    if el and el.find('img'):
        content_html += add_image(el)

    for el in soup.find_all(class_=re.compile(r'item--paragraph--type--')):
        it = el.find(class_='field--name-field-subhead')
        if it:
            content_html += '<h3>{}</h3>'.format(it.get_text())
        if 'item--paragraph--type--body' in el['class']:
            it = el.find(class_='field--name-field-paragraph-body')
            if it and it.body:
                content_html += it.body.decode_contents()
            elif el.find(class_='field--name-field-subhead'):
                pass
            else:
                logger.warning('unhandled item--paragraph--type--body in ' + item['url'])
        elif 'item--paragraph--type--photographs' in el['class']:
            it = el.find(class_='article-images-wrapper')
            content_html += add_image(it)
        elif 'item--paragraph--type--video' in el['class']:
            if el.find(class_='brightcove-player'):
                it = el.find('video-js')
                content_html += utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(it['data-account'], it['data-player'], it['data-video-id']))
            else:
                logger.warning('unhandled video in ' + item['url'])
        elif 'item--paragraph--type--embed' in el['class']:
            it = el.find(class_='field--name-field-embed-code')
            if it and it.iframe:
                content_html += utils.add_embed(it.iframe['src'])
            elif re.search(r'Subscribe to', el.get_text(), flags=re.I):
                pass
            else:
                logger.warning('unhandled embed in ' + item['url'])
        elif 'item--paragraph--type--factbox' in el['class']:
            title = el.find(class_='paragraph-inline-title').get_text()
            if re.search(r'Find it in our digital edition', title, flags=re.I):
                continue
            if el.img:
                img_src = '{}/image?url={}&width=128'.format(config.server, quote_plus(el.img['src']))
                content_html += '<table><tr><td><img src="{}"/></td><td style="vertical-align:top;"><h4 style="margin:0;">{}</h4><small>{}</small></td></tr></table>'.format(img_src, title, el.p.decode_contents())
            else:
                content_html += '<blockquote><strong>{}:</strong>{}</blockquote>'.format(title, el.p.decode_contents())
        elif 'item--paragraph--type--related' in el['class']:
            pass
        elif 'item--paragraph--type--newsletter-widget-v1' in el['class']:
            pass
        else:
            logger.warning('unhandled paragraph type {} in {}'.format(el['class'], item['url']))

    content_soup = BeautifulSoup(content_html, 'html.parser')
    for el in content_soup.find_all('script'):
        el.decompose()

    item['content_html'] = str(content_soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
