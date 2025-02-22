import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    video_id = ''
    if 'embed' in paths:
        video_id = paths[-1]
    elif paths[-1].endswith('.html'):
        oembed_json = utils.get_url_json('https://rumble.com/api/Media/oembed.json?url=' + quote_plus(url))
        if oembed_json:
            m = re.search(r'https://rumble\.com/embed/[^"]+', oembed_json['html'])
            if m:
                embed_url = m.group(0)
                paths = list(filter(None, urlsplit(embed_url).path[1:].split('/')))
                video_id = paths[1]
    if not video_id:
        logger.warning('unable to determine video id for ' + url)
        return None

    embed_url = 'https://rumble.com/embedJS/u3/?request=video&ver=2&v={}&ext=%7B%22ad_count%22%3Anull%7D&ad_wt=17'.format(video_id)
    # print(embed_url)
    player_json = utils.get_url_json(embed_url)
    if not player_json:
        embed_url = 'https://rumble.com/embed/' + video_id + '/'
        embed_html = utils.get_url_html(embed_url)
        if not embed_html:
            return None
        if save_debug:
            utils.write_file(embed_html, './debug/debug.html')
        m = re.search(r'\["{}"\]=({{.*?}});\w'.format(paths[1]), embed_html)
        if not m:
            logger.warning('unable to parse rumble player data in ' + url)
            return None
        player_data = re.sub(r',loaded:[^},]+', '', m.group(1))
        player_json = json.loads(player_data)

    if not player_json:
        logger.warning('unable to get player data for ' + url)
        return None

    if save_debug:
        utils.write_file(player_json, './debug/video.json')

    item = {}
    item['id'] = video_id
    item['url'] = 'https://rumble.com' + player_json['l']
    item['title'] = player_json['title']
    dt = datetime.fromisoformat(player_json['pubDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    item['author'] = {"name": player_json['author']['name']}
    item['image'] = player_json['i']
    item['_video'] = player_json['u']['mp4']['url']
    caption = '{} | <a href="{}">Watch on Rumble</a>'.format(item['title'], item['url'])
    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['image'], caption, use_videojs=True)

    if 'embed' in args:
        return item

    page_html = utils.get_url_html(item['url'])
    if page_html:
        page_soup = BeautifulSoup(page_html, 'lxml')
        desc = page_soup.find('div', attrs={"data-js": "media_long_description_container"})
        if desc:
            for el in desc.find_all('button', class_=['media-description--show-button', 'media-description--hide-button']):
                el.decompose()
            for el in desc.find_all('p', class_=True):
                el.attrs = {}
            for el in desc.find_all('a', attrs={"onclick": True}):
                el.unwrap()
            item['content_html'] += desc.decode_contents()

        item['tags'] = []
        for el in page_soup.select('div.media-description-tags-container > a.video-category-tag'):
            item['tags'].append(el.get_text().strip())
        if len(item['tags']) == 0:
            del item['tags']

    return item


def get_feed(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'lxml')

    n = 0
    feed_items = []
    for el in page_soup.select('div.videostream > div.videostream__footer > a.title__link'):
        video_url = 'https://rumble.com' + el['href']
        if save_debug:
            logger.debug('getting content for ' + video_url)
        item = get_content(video_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
