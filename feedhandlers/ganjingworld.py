import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return 'https://on3static.com/cdn-cgi/image/width={},quality=70/{}'.format(width, img_src)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    path = '/' + config.locale
    if len(paths) > 0:
        if split_url.path.endswith('/'):
            path += split_url.path[:-1]
        else:
            path += split_url.path
    path += '.json'
    if 'hashtag' in paths:
        query = parse_qs(split_url.query)
        if query.get('tab'):
            path += '?tab=' + query['tab'][0]
        else:
            path += '?tab=All'
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    print(next_url)
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
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    if next_data['pageProps'].get('video'):
        video_json = next_data['pageProps']['video']
    elif next_data['pageProps'].get('short'):
        video_json = next_data['pageProps']['short']
    return get_item(video_json, args, site_json, save_debug)


def get_item(video_json, args, site_json, save_debug):
    item = {}
    item['id'] = video_json['id']
    if video_json['type'] == 'Video':
        item['url'] = 'https://www.ganjingworld.com/video/' + video_json['id']
    elif video_json['type'] == 'Shorts':
        item['url'] = 'https://www.ganjingworld.com/short/' + video_json['id']
    item['title'] = video_json['title']

    dt = datetime.fromtimestamp(video_json['created_at'] / 1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = video_json['channel']['name']
    item['author']['url'] = 'https://www.ganjingworld.com/channel/' + video_json['channel']['id']
    if video_json['channel'].get('icon'):
        avatar = '{}/image?url={}&height=32&mask=ellipse'.format(config.server, quote_plus(video_json['channel']['icon']))
    else:
        avatar = '{}/image?height=32&width=32&mask=ellipse'.format(config.server)

    item['tags'] = []
    if video_json.get('keywords'):
        for it in video_json['keywords']:
            item['tags'].append(it.strip())
    if video_json.get('hashtags'):
        item['tags'] += video_json['hashtags']
    elif video_json.get('link_hashtags'):
        item['tags'] += video_json['link_hashtags']

    if video_json.get('poster_hd_url'):
        item['_image'] = video_json['poster_hd_url']
    elif video_json.get('poster_url'):
        item['_image'] = video_json['poster_url']
    else:
        logger.warning('unknown poster url in ' + item['url'])

    if video_json.get('video_url'):
        item['_video'] = video_json['video_url']
    elif video_json.get('meta') and video_json['meta'].get('video_url'):
        item['_video'] = video_json['meta']['video_url']
    else:
        logger.warning('unknown video url in ' + item['url'])

    if video_json.get('description'):
        item['summary'] = video_json['description']

    heading = '<table><tr><td style="width:32px; verticle-align:middle;"><img src="{}" /><td style="verticle-align:middle;"><a href="{}">{}</a></td></tr></table>'.format(avatar, item['author']['url'], item['author']['name'])
    caption = '{} | <a href="{}">Watch on Gan Jing World</a>'.format(item['title'], item['url'])
    item['content_html'] = utils.add_video(item['_video'], 'application/x-mpegURL', item['_image'], caption, heading=heading)
    return item


def get_feed(url, args, site_json, save_debug=False):
    videos = []
    shorts = []
    split_url = urlsplit(url)
    query = parse_qs(split_url.query)
    paths = list(filter(None, split_url.path.split('/')))
    if 'channel' in paths:
        channel_id = paths[paths.index('channel') + 1]
        if query.get('tab'):
            content_type = query['tab'][0].title()
        else:
            content_type = 'All'
        if content_type == 'Video' or content_type == 'All':
            api_url = 'https://gw.ganjingworld.com/v1.1/content/get-by-channel?lang={}&channel_id={}&page_size=8&content_type=Video&include_hidden=true&query=basic,view&visibility=public&mode=ready'.format(config.locale, channel_id)
            api_json = utils.get_url_json(api_url)
            if api_json:
                videos = api_json['data']['list']
        if content_type == 'Shorts' or content_type == 'All':
            api_url = 'https://gw.ganjingworld.com/v1.1/content/get-by-channel?lang={}&channel_id={}&page_size=8&content_type=Shorts&include_hidden=true&query=basic,view&visibility=public&mode=ready'.format(config.locale, channel_id)
            api_json = utils.get_url_json(api_url)
            if api_json:
                shorts = api_json['data']['list']
    elif 'hashtag' in paths:
        hashtag = paths[paths.index('hashtag') + 1].lower()
        if query.get('tab'):
            content_type = query['tab'][0]
        else:
            content_type = 'All'
        if content_type == 'Video' or content_type == 'All':
            api_url = 'https://gw.ganjingworld.com/v1.0c/hashtag/get-contents?hashtag=%23{}&type=AllVideo&page_size=12&hide_by_owner=true&lang={}'.format(hashtag, config.locale)
            api_json = utils.get_url_json(api_url)
            if api_json:
                videos = api_json['data']['list']
        if content_type == 'Shorts' or content_type == 'All':
            api_url = 'https://gw.ganjingworld.com/v1.0c/hashtag/get-contents?hashtag=%23{}&type=AllShorts&page_size=12&hide_by_owner=true&lang={}'.format(hashtag, config.locale)
            api_json = utils.get_url_json(api_url)
            if api_json:
                shorts = api_json['data']['list']
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')

    if not (videos or shorts):
        return None

    if save_debug:
        utils.write_file(videos + shorts, './debug/feed.json')

    n = 0
    feed_items = []
    for video in videos + shorts:
        if save_debug:
            logger.debug('getting content for ' + video['id'])
        item = get_item(video, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if 'channel' in paths:
        feed['title'] = '{} {} | Gan Jin World'.format(feed_items[0]['author']['name'], content_type)
    if 'hashtag' in paths:
        feed['title'] = '#{} {} | Gan Jin World'.format(hashtag, content_type)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
