import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    m = re.search(r'"post_id":(\d+)', page_html)
    if not m:
        logger.warning('unable to determine post id in ' + url)
        return None
    post_url = 'https://www.seattletimes.com/wp-json/hub/post/{}'.format(m.group(1))
    post_json = utils.get_url_json(post_url)
    if not post_json:
        logger.warning('failed to get post data from ' + post_url)
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['permalink']
    item['title'] = post_json['title']

    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromtimestamp(post_json['created_at'])
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_est = datetime.fromtimestamp(post_json['modified_at'])
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in post_json['authors']:
        authors.append(author['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = post_json['section_list'].copy()

    if post_json.get('teaser_image'):
        item['_image'] = post_json['teaser_image']['sizes']['auto_medium']
    elif post_json.get('images'):
        item['_image'] = post_json['images'][0]['sizes']['auto_medium']

    item['summary'] = post_json['abstract']

    content = BeautifulSoup(post_json['post_content'], 'html.parser')

    for el in content.find_all(class_=re.compile(r'\bad\b|marketing-placeholder|manual-related|most-read|ndn_embed|related-article-link|sendtonews-embed|user-messaging')):
        el.decompose()

    for el in content.find_all(class_='st-image-gallery'):
        gallery_data = json.loads(el['data-gallery'])
        if save_debug:
            utils.write_file(gallery_data, './debug/gallery.json')
        for gallery_image in gallery_data['images']:
            img_src = ''
            if post_json.get('inlime_images'):
                image = next((it for it in post_json['inline_images'] if it['id'] == gallery_image['id']), None)
                if image:
                    img_src = image['sizes']['auto_medium']
                    caption = image.get('caption')
            if not img_src:
                if gallery_image.get('srcset'):
                    img_src = utils.image_from_srcset(gallery_image['srcset'], 1000)
                else:
                    img_src = gallery_image['src']
                caption = gallery_image.get('caption')
            new_html = utils.add_image(img_src, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_before(new_el)
        el.decompose()

    for el in content.find_all(class_='youtube-embed-container'):
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_before(new_el)
            el.decompose()
        else:
            logger.warning('unhandled youtube-embed-container in ' + item['url'])

    for el in content.find_all(class_='embed-container'):
        if el.name == None:
            continue
        new_html = ''
        if 'youtube' in el['class']:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        elif 'article-component' in el['class']:
            it = el.find('h2')
            if it and re.search(r'^More on', it.get_text().strip(), flags=re.I):
                el.decompose()
                continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_before(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embed-container in ' + item['url'])

    for el in content.find_all(class_='fact-box'):
        el.name = 'blockquote'
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
        del el['class']
        it = el.find(class_='fact-box-wrapper')
        if it:
            it.unwrap()
        it = el.find(class_='fact-box-label')
        if it.get_text().strip():
            del it['class']
        else:
            it.decompose()
        it = el.find(class_='fact-box-headline')
        if it.get_text().strip():
            it.name = 'h3'
            del it['class']
        else:
            it.decompose()
        it = el.find(class_='fact-box-body')
        if it.get_text().strip():
            it.unwrap()
        else:
            it.decompose()
        it = el.find(class_='fact-box-embed-text-more')
        if it.get_text().strip():
            it.unwrap()
        else:
            it.decompose()
        it = el.find(class_='show-hide-btn')
        if it:
            it.decompose()

    for el in content.find_all('a', class_=True):
        del el['class']

    item['content_html'] = ''
    if post_json.get('images'):
        image = post_json['images'][0]
        item['content_html'] += utils.add_image(image['sizes']['auto_medium'], image.get('caption'))

    item['content_html'] += str(content)

    if post_json.get('images') and len(post_json['images']) > 1:
        item['content_html'] += '<h3>Photo gallery</h3>'
        for image in post_json['images']:
            item['content_html'] += utils.add_image(image['sizes']['auto_medium'], image.get('caption'))

    item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
