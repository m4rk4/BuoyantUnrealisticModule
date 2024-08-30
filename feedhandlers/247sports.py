import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs

import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    # https://s3media.247sports.com/Uploads/Assets/111/281/12281111.jpg?fit=bounds&crop=620:320,offset-y0.50&width=620&height=320
    if 's3media.247sports.com' in img_src:
        return utils.clean_url(img_src) + '?width={}'.format(width)
    return img_src


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'__INITIAL_DATA__'))
    if not el:
        logger.warning('unable to find __INITIAL_DATA__ in ' + url)
        return None

    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    # utils.write_file(el.string[i:j], './debug/data.txt')
    initial_data = json.loads(el.string[i:j].replace('undefined', 'null'))
    if save_debug:
        utils.write_file(initial_data, './debug/debug.json')

    article_json = initial_data['main']['headlineList'][0]
    item = {}
    item['id'] = article_json['key']
    item['url'] = article_json['canonicalUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": article_json['author']['author']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    if article_json.get('assetUrl'):
        item['image'] = article_json['assetUrl']

    if article_json.get('seo'):
        item['summary'] = article_json['seo']

    item['content_html'] = ''
    if article_json.get('teaser'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['teaser'])

    body = BeautifulSoup(article_json['body'], 'html.parser')
    for el in body.find_all('blockquote', recursive=False):
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in body.find_all('figure', recursive=False):
        new_html = ''
        it = el.find('img')
        if it:
            img_src = resize_image(it['data-src'])
            captions = []
            it = el.select('figcaption > em')
            if it:
                captions.append(it[0].decode_contents())
            it = el.select('figcaption > span.meta')
            if it:
                captions.append(it[0].decode_contents())
            new_html = utils.add_image(img_src, ' | '.join(captions))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled figure in ' + item['url'])

    for el in body.find_all(class_='embedVideo'):
        new_html = ''
        data_values = parse_qs(html.unescape(el['data-values']))
        print('https://www.cbssports.com/api/content/video/?id=' + data_values['id'][0])
        video_json = utils.get_url_json('https://www.cbssports.com/api/content/video/?id=' + data_values['id'][0])
        if video_json:
            video = next((it for it in video_json[0]['metaData']['files'] if it['format'] == 'm3u8'), None)
            if not video:
                video = utils.closest_dict(video_json[0]['metaData']['files'], 'bitrate', 1000000)
            if video['format'] == 'm3u8':
                new_html = utils.add_video(video['url'], 'application/x-mpegURL', video_json[0]['image']['path'], video_json[0]['title'])
            else:
                new_html = utils.add_video(video['url'], 'video/mp4', video_json[0]['image']['path'], video_json[0]['title'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embedVideo in ' + item['url'])

    for el in body.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')

        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in body.find_all(class_='vip-gate-container'):
        el.decompose()

    item['content_html'] += str(body)
    return item
