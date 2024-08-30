import json, re
from bs4 import BeautifulSoup
from curl_cffi import requests
from datetime import datetime
from urllib.parse import unquote_plus, urlsplit

import config, utils
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


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    post_json = None
    def find_post(child):
        nonlocal post_json
        if not isinstance(child, list):
            return
        if isinstance(child[0], str) and child[0] == '$':
            if child[3].get('post'):
                post_json = child[3]['post']
            elif child[3].get('data-testid') and child[3]['data-testid'] == 'ad-container':
                return
            elif child[3].get('children'):
                iter_children(child[3]['children'])
        else:
            iter_children(child)
    def iter_children(children):
        nonlocal post_json
        if isinstance(children, list):
            if isinstance(children[0], str) and children[0] == '$':
                find_post(children)
            else:
                for child in children:
                    find_post(child)
                    if post_json:
                        break
    iter_children(next_json['2'])
    if not post_json:
        logger.warning('unable to find post')
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['yoastHeadJson']['canonical']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['yoastHeadJson']['article_published_time'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['yoastHeadJson']['article_modified_time'])
    item['date_modified'] = dt.isoformat()

    if post_json.get('authors'):
        authors = []
        for it in post_json['authors']:
            authors.append(it['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))


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

    if post_json.get('featuredImg'):
        item['_image'] = resize_image(post_json['featuredImg']['src'])
        if post_json['featuredImg'].get('caption'):
            caption = re.sub(r'</?p>', '', post_json['featuredImg']['caption'].strip())
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    content_html = ''
    for content in post_json['content']:
        for it in content:
            if it.startswith('<p><figure'):
                el = BeautifulSoup(it, 'html.parser')
                el.p.insert_before(el.figure)
                new_html = str(el)
            elif it.startswith('<p><div'):
                el = BeautifulSoup(it, 'html.parser')
                el.p.insert_before(el.div)
                new_html = str(el)
            elif it.startswith('<p><iframe'):
                el = BeautifulSoup(it, 'html.parser')
                el.p.insert_before(el.iframe)
                new_html = str(el)
            elif re.search(r'^\$[0-9a-f]+', it):
                m = re.search(r'^\$([0-9a-f]+)', it)
                new_html = next_json[m.group(1)]
            else:
                new_html = it
            content_html += new_html

    soup = BeautifulSoup(content_html, 'html.parser')

    for el in soup.find_all('figure', class_=['image-wrapper', 'wp-block-image']):
        new_html = ''
        if el.figcaption:
            caption = el.figcaption.decode_contents()
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
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
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
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled video-wrapper in ' + url)

    for el in soup.find_all(class_='twitter-tweet'):
        tweet_url = el.find_all('a')[-1]['href']
        new_html = utils.add_embed(tweet_url)
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el.find_parent('figure', class_='wp-block-embed')
        if it:
            it.replace_with(new_el)
        else:
            el.replace_with(new_el)

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(class_='perfect-pullquote'):
        new_html = utils.add_pullquote(str(el.blockquote.p))
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    for el in soup.find_all(class_=True):
        if 'wp-block-heading' in el['class'] or 'wp-block-separator' in el['class']:
            el.attrs = {}
        else:
            logger.warning('unhandled element {} with class {} in {}'.format(el.name, el['class'], url))

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def get_next_json(url, save_debug):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        # "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22idOrSlug%22%2C%22technology%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "next-url": "/technology",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"124\", \"Microsoft Edge\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    r = requests.get(url, headers=headers, impersonate=config.impersonate, proxies=config.proxies)
    if not r or r.status_code != 200:
        logger.warning('unable to get next data from ' + url)
        return None

    next_data = r.text
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = {}
    x = 0
    m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        x += len(key) + 1
        val = m.group(2)
        if val.startswith('I'):
            val = val[1:]
            x += 1
        elif val.startswith('T'):
            t = re.search(r'T([0-9a-f]+),(.*)', val)
            if t:
                n = int(t.group(1), 16)
                x += len(t.group(1)) + 2
                val = next_data[x:x + n]
                if not val.isascii():
                    i = n
                    n = 0
                    for c in val:
                        n += 1
                        i -= len(c.encode('utf-8'))
                        if i == 0:
                            break
                    val = next_data[x:x + n]
        if val:
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json

