import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    if not '/wp-cms/' in img_src:
        return img_src
    return img_src.replace('/wp-cms/', '/w_{},c_fill,g_auto,f_auto,q_auto,fl_lossy/wp-cms/'.format(width))

def add_video(video_id):
    jw_json = utils.get_url_json('https://content.jwplatform.com/feeds/{}.json'.format(video_id))
    if not jw_json:
        return ''
    video_sources = []
    for vid_src in jw_json['playlist'][0]['sources']:
        if vid_src['type'] == 'video/mp4':
            video_sources.append(vid_src)
    vid_src = utils.closest_dict(video_sources, 'height', 480)
    poster = utils.closest_dict(jw_json['playlist'][0]['images'], 'width', 1080)
    if jw_json.get('title'):
        caption = jw_json['title']
    else:
        caption = ''
    return utils.add_video(vid_src['file'], 'video/mp4', poster['src'], caption)


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = 'https://fc-api.fastcompany.com/api/v3/post-related/fastcompany/' + paths[0]
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    post_json = api_json['post']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['link']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['structuredData']['published'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['structuredData']['modified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    author = {"name": post_json['author']['name']}

    item['tags'] = []
    if post_json.get('categories'):
        for it in post_json['categories']:
            item['tags'].append(it['name'])
    if post_json.get('tags'):
        for it in post_json['tags']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if post_json.get('featured_image'):
        item['_image'] = resize_image(post_json['featured_image']['source'])
        item['content_html'] += utils.add_image(item['_image'], post_json['featured_image']['caption'])

    content_html = ''
    for content in post_json['content']:
        for it in content:
            if it.startswith('<p><figure'):
                el = BeautifulSoup(it, 'html.parser')
                el.p.insert_before(el.figure)
                it = str(el)
            elif it.startswith('<p><div'):
                el = BeautifulSoup(it, 'html.parser')
                el.p.insert_before(el.div)
                it = str(el)
            content_html += it

    soup = BeautifulSoup(content_html, 'html.parser')

    for el in soup.find_all('figure', class_='image-wrapper'):
        new_html = ''
        if el.figcaption:
            caption = el.figcaption.get_text()
        else:
            caption = ''
        if el.img:
            img_src = el.img.get('data-src')
            if not img_src:
                img_src = el.img.get('src')
            if img_src:
                new_html = utils.add_image(resize_image(img_src), caption)
        elif el.video:
            new_html = utils.add_video(el.source['src'], el.source['type'], resize_image(el.video['poster']), caption)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled image-wrapper in ' + url)

    for el in soup.find_all('figure', class_='video-wrapper'):
        new_html = ''
        if el.iframe:
            if 'youtube' in el.iframe['src']:
                new_html = utils.add_embed(el.iframe['src'])
            elif 'fastcompany.com/embed' in el.iframe['src']:
                split_url = urlsplit(el.iframe['src'])
                paths = list(filter(None, split_url.path.split('/')))
                new_html = add_video(paths[1])
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled video-wrapper in ' + url)

    for el in soup.find_all(class_='twitter-tweet'):
        tweet_url = el.find_all('a')[-1]['href']
        new_html = utils.add_embed(tweet_url)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all(class_='perfect-pullquote'):
        new_html = utils.add_pullquote(str(el.blockquote.p))
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    for el in soup.find_all(class_=True):
        logger.warning('unhandled element {} with class {} in {}'.format(el.name, el['class'], url))

    item['content_html'] += str(soup)
    return item

def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
