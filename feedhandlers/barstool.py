import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    if len(paths) == 3 and paths[0] == 'blog':
        next_url += '?id={}&slug={}'.format(paths[1], paths[2])
    else:
        next_url += '?slug=' + paths[-1]
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    # next_data = get_next_data(url, site_json)
    # if not next_data:
    #     return None
    # story_json = next_data['pageProps']['story']
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if not paths[1].isnumeric():
        logger.warning('unhandled url ' + url)
        return None
    story_json = utils.get_url_json('https://union.barstoolsports.com/v2/stories/' + paths[1])
    if not story_json:
        return None
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item['id'] = story_json['id']
    item['url'] = story_json['url']
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_json.get('updated_at'):
        dt = datetime.fromisoformat(story_json['updated_at'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": story_json['author']['name']}

    item['tags'] = []
    for it in story_json['category']:
        item['tags'].append(it['name'])
    if story_json.get('tag'):
        item['tags'].append(story_json['tag'])
    if story_json.get('tags'):
        item['tags'] += story_json['tags']
    elif story_json.get('content_tags'):
        for it in story_json['content_tags']:
            item['tags'].append(it['tag'])

    if story_json.get('thumbnail'):
        item['_image'] = story_json['thumbnail']['raw']

    item['content_html'] = ''
    if 'video' in paths:
        video_json = utils.get_url_json('https://union.barstoolsports.com/v2/stories/{}/video-source'.format(item['id']))
        if video_json:
            video = next((it for it in video_json['sources'] if it['type'] == 'application/x-mpegURL'), None)
            if not video:
                video = next((it for it in video_json['sources'] if it['type'] == 'video/mp4' and it.get('height') and it['height'] == 480), None)
                if not video:
                    video = video_json['sources']
            item['content_html'] = utils.add_video(video['src'], video['type'], video_json['poster'], video_json['name'])

    soup = BeautifulSoup(story_json['post_type_meta']['standard_post']['raw_content'], 'html.parser')
    for el in soup.find_all(id='Article-Ad-Placeholder'):
        el.decompose()

    for el in soup.find_all(class_='oembed__wrapper'):
        new_html = ''
        if el.find(class_='iframely-embed'):
            it = el.find('a', attrs={"data-iframely-url": True})
            if it:
                if '/store.barstoolsports.com/' in it['href']:
                    el.decompose()
                    continue
                else:
                    new_html = utils.add_embed(it['href'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled oembed__wrapper in ' + item['url'])

    for el in soup.find_all(class_='hq-image'):
        new_html = ''
        if el.img:
            if el.img.get('srcset'):
                img_src = utils.image_from_srcset(el.img['srcset'], 1080)
            else:
                img_src = el.img['src']
            it = el.find(class_='image-attribution')
            if it:
                caption = el.decode_contents()
            else:
                caption = ''
            new_html = utils.add_image(img_src, caption)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled hq-image in ' + item['url'])

    for el in soup.find_all('img', recursive=False):
        if el.get('srcset'):
            img_src = utils.image_from_srcset(el['srcset'], 1080)
        else:
            img_src = el['src']
        new_html = utils.add_image(img_src)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('blockquote', recursive=False):
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for story in next_data['pageProps']['items']:
        if save_debug:
            logger.debug('getting content for ' + story['url'])
        item = get_content(story['url'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if next_data['pageProps'].get('category'):
        feed['title'] = next_data['pageProps']['category']['name'] + ' | Barstool Sports'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
