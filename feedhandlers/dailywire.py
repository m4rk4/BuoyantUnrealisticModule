import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return utils.clean_url(img_src) + '?fit=crop&w={}&auto=format&ixlib=react-9.3.0'.format(width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
    next_url = '{}://{}/_next/data/{}/{}.json'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    #print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
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
    if next_data['pageProps'].get('post'):
        return get_post(next_data['pageProps']['post'], args, site_json, save_debug)
    elif next_data['pageProps'].get('episode'):
        return get_episode(next_data['pageProps']['episode'], args, site_json, save_debug)
    elif next_data['pageProps'].get('episodeData'):
        return get_episode(next_data['pageProps']['episodeData']['episode'], args, site_json, save_debug)
    else:
        logger.warning('unhandled url ' + url)
        return None


def get_episode(episode_json, args, site_json, save_debug):
    item = {}
    item['id'] = episode_json['id']

    if episode_json.get('podcast'):
        item['url'] = 'https://www.dailywire.com/podcasts/{}/{}'.format(episode_json['podcast']['slug'], episode_json['slug'])
        item['author'] = {
            "name": episode_json['podcast']['name'],
            "url": 'https://www.dailywire.com/podcasts/' + episode_json['podcast']['slug']
        }
    elif episode_json.get('show'):
        item['url'] = 'https://www.dailywire.com/episode/' + episode_json['slug']
        item['author'] = {
            "name": episode_json['show']['name'],
            "url": 'https://www.dailywire.com/show/' + episode_json['show']['slug']
        }

    item['title'] = episode_json['title']

    # TODO: is date UTC?
    dt = datetime.fromisoformat(episode_json['createdAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)
    if episode_json.get('updatedAt'):
        dt = datetime.fromisoformat(episode_json['updatedAt']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    if episode_json.get('image'):
        item['_image'] = episode_json['image']
    elif episode_json.get('thumbnail'):
        item['_image'] = episode_json['thumbnail']

    if episode_json.get('description'):
        item['summary'] = episode_json['description']

    if episode_json.get('segments'):
        for segment in episode_json['segments']:
            caption = 'Watch: <a href="{}">{}</a> ({})'.format(item['url'], item['title'], segment['title'])
            if segment['video'] == 'Access Denied':
                item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
            else:
                item['content_html'] = utils.add_video(segment['video'], 'application/x-mpegURL', item['_image'], caption)
    elif episode_json.get('podcast'):
        item['_audio'] = 'https://stream.media.dailywire.com/{}.m3u8'.format(episode_json['audioMuxPlaybackId'])
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'application/x-mpegURL'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] = utils.add_audio(item['_audio'], item['_image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], episode_json['duration'], 'application/x-mpegURL')

    if 'embed' not in args and episode_json.get('description'):
        item['content_html'] += '<p>' + episode_json['description'] + '</p>'
    return item


def get_post(post_json, args, site_json, save_debug):
    item = {}
    item['id'] = post_json['id']
    item['url'] = 'https://www.dailywire.com/news/' + post_json['slug']
    item['title'] = post_json['title']

    # TODO: is date UTC?
    dt = datetime.fromisoformat(post_json['date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if post_json.get('modified'):
        dt = datetime.fromisoformat(post_json['modified']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = post_json['author']['name']

    item['tags'] = []
    if post_json.get('categories'):
        item['tags'] += [it['name'] for it in post_json['categories']]
    if post_json.get('topics'):
        item['tags'] += [it['name'] for it in post_json['topics']]
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    if post_json.get('subhead'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subhead'])

    if post_json.get('image'):
        item['_image'] = post_json['image']['url']
        if post_json['image'].get('caption'):
            caption = re.sub(r'^<p>(.*?)</p>', r'\1', post_json['image']['caption'].strip())
        else:
            caption = ''
        item['content_html'] += utils.add_image(resize_image(item['_image']), caption)

    item['content_html'] += wp_posts.format_content(post_json['content'], item, site_json)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss.xml' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for post in next_data['pageProps']['posts']:
        if save_debug:
            post_url = 'https://www.dailywire.com/news/' + post['slug']
            logger.debug('getting content for ' + post_url)
        item = get_post(post, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed