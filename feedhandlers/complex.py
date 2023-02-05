import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, unquote_plus

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    return 'https://images.complex.com/images/c_fill,f_auto,g_center,w_{}/fl_lossy,pg_1/{}/{}'.format(width, paths[-2], paths[-1])


def get_image_src(image, width=1080):
    return 'https://images.complex.com/images/c_fill,f_auto,g_center,w_{}/fl_lossy,pg_1/{}/{}'.format(width, image['transformation']['asset']['cloudinaryId'], image['transformation']['asset']['seoFilename'])


def add_media(media):
    if media['class'] == 'Image':
        media_html = utils.add_image(get_image_src(media), media['caption'])
    elif media['class'] == 'YoutubeVideo':
        media_html = utils.add_embed(media['url'])
    elif media['class'] == 'JWVideo':
        media_html = utils.add_embed('https://cdn.jwplayer.com/players/{}-'.format(media['jwId']))
    else:
        logger.warning('unhandled media class ' + media['class'])
        media_html = ''
    return media_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = 'https://www.complex.com/api/article/resolve/alias?value=' + paths[-1]
    article_json = utils.get_url_json(api_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['headline']

    # Not sure of the timezone
    dt = datetime.fromtimestamp(article_json['dateCreated']/1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromtimestamp(article_json['dateUpdated']/1000).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for it in article_json['tags']:
        item['tags'].append(it['displayText'])
    if not item.get('tags'):
        del item['tags']

    if article_json.get('thumbnail'):
        item['_image'] = get_image_src(article_json['thumbnail'])

    item['summary'] = article_json['metaDescription']

    item['content_html'] = ''
    if article_json.get('leadCarousel'):
        for it in article_json['leadCarousel']:
            item['content_html'] += add_media(it)

    content = article_json['content']
    if article_json.get('slides'):
        for slide in article_json['slides']:
            content += '<h2>{}</h2>'.format(slide['headline'])
            if slide.get('leadCarousel'):
                for it in slide['leadCarousel']:
                    content += add_media(it)
            content += slide['content']

    soup = BeautifulSoup(content, 'html.parser')
    for el in soup.find_all('script'):
        el.decompose()

    for el in soup.find_all(class_='custom-embed'):
        if not el.contents:
            el.decompose()
            continue
        new_html = ''
        it = el.find('blockquote')
        if it and it.get('class'):
            if 'twitter-tweet' in it['class']:
                links = it.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif 'instagram-media' in it['class']:
                new_html = utils.add_embed(it['data-instgrm-permalink'])
        else:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled custom-embed in ' + item['url'])

    for el in soup.find_all('blockquote'):
        links = el.find_all('a')
        if links:
            if re.search(r'https://twitter\.com/[^/]+/status/\d+', links[-1]['href']):
                new_html = utils.add_embed(links[-1]['href'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

    for el in soup.find_all(class_='image'):
        it = el.find('img')
        if it:
            img_src = resize_image(it['src'])
            it = el.find('figcaption')
            if it:
                caption = it.get_text()
            else:
                caption = ''
            new_html = utils.add_image(img_src, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'div' and el.parent.get('style') and re.search(r'text-align', el.parent['style']):
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled image in ' + item['url'])

    item['content_html'] += str(soup)

    if article_json.get('scenes'):
        for scene in article_json['scenes']:
            if len(scene['sceneType']['config']) > 1:
                logger.warning('unhandled scene with multiple types in ' + item['url'])
            if scene['sceneType']['config'][0][0]['type'] == 'richtext':
                for it in scene['richtexts']:
                    item['content_html'] += it
            elif scene['sceneType']['config'][0][0]['type'] == 'image':
                for it in scene['leadCarousel']:
                    img_src = 'https://images.complex.com/complex/images/c_scale,f_auto,q_auto,w_1080/fl_lossy,pg_1/{}/{}'.format(it['transformation']['asset']['cloudinaryId'], it['transformation']['asset']['seoFilename'])
                    item['content_html'] += utils.add_image(img_src, it['transformation']['asset']['caption'])
            else:
                logger.warning('unhandled scene type {} in {}'.format(scene['sceneType']['config'][0][0]['type'], item['url']))
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
