import feedparser
import dateutil.parser
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if url.startswith('https://player.'):
        feed_url = 'https://feeds.castfire.com' + urlsplit(url).path
        feed_html = utils.get_url_html(feed_url)
        if not feed_html:
            return None
        try:
            podcast_feed = feedparser.parse(feed_html)
        except:
            logger.warning('feedparser error ' + feed_url)
            return None

        if save_debug:
            utils.write_file(podcast_feed, './debug/podcast.json')

        return add_episode(podcast_feed['entries'][0], podcast_feed, url, args)
    elif url.startswith('https://rss.'):
        feed_html = utils.get_url_html(url)
        if not feed_html:
            return None
        try:
            podcast_feed = feedparser.parse(feed_html)
        except:
            logger.warning('Feedparser error ' + url)
            return None
        if save_debug:
            utils.write_file(podcast_feed, './debug/debug.json')
        return add_podcast(podcast_feed, url, args)
    else:
        logger.warning('unhandled feed url ' + url)
        return None


def add_podcast(podcast_feed, url, args):
    item = {}

    paths = list(filter(None, urlsplit(url).path[1:].split('/')))
    item['id'] = paths[-1]

    item['url'] = url
    item['title'] = podcast_feed['feed']['title']

    dt = dateutil.parser.parse(podcast_feed['feed']['updated'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {
        "name": podcast_feed['feed']['title']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if podcast_feed['feed'].get('tags'):
        item['tags'] = []
        for it in podcast_feed['feed']['tags']:
            if it['term'].lower() not in item['tags']:
                item['tags'].append(it['term'].lower())

    item['image'] = podcast_feed['feed']['image']['href']
    poster = '{}/image?url={}&overlay=audio'.format(config.server, quote_plus(item['image']))

    if podcast_feed['feed'].get('subtitle'):
        item['summary'] = podcast_feed['feed']['subtitle']

    item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
    item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="{}/playlist?url={}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(config.server, quote_plus(item['url']), poster)
    item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
    if item.get('summary'):
        item['content_html'] += '<div style="margin:4px 0 4px 0;">{}</div>'.format(item['summary'])
    item['content_html'] += '</div></div>'
    item['content_html'] += '<h3>Episodes:</h3>'
    item['_playlist'] = []
    for i, episode in enumerate(podcast_feed['entries'][:10]):
        ep = add_episode(episode, podcast_feed, url, args)
        if i < 5:
            item['content_html'] += utils.add_audio(ep.get('_audio'), ep['image'], ep['title'], ep['url'], '', '', ep['_display_date'], episode['itunes_duration'].lstrip('0:'), show_poster=False)
        item['_playlist'].append({
            "src": ep.get('_audio'),
            "name": ep['_display_title'] + ' &ndash; ' + ep['title'],
            "artist": ep['author']['name'],
            "image": ep['image']
        })
    return item


def add_episode(episode, podcast_feed, url, args):
    item = {}

    if episode.get('links'):
        audio = next((it for it in episode['links'] if it['type'] == 'audio/mpeg' or it['type'] == 'audio/mp3'), None)
    if not audio and episode.get('media_content'):
        audio = next((it for it in episode['media_content'] if it['type'] == 'audio/mpeg' or it['type'] == 'audio/mp3'), None)
    if audio:
        item['_audio'] = audio['href']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)

    item['id'] = episode['id']

    item['title'] = episode['title']

    item['author'] = {}
    if episode.get('castfire_channelname'):
        item['author']['name'] = episode['castfire_channelname']
    elif podcast_feed['feed'].get('title'):
        item['author']['name'] = podcast_feed['feed']['title']
    item['authors'] = []
    item['authors'].append(item['author'])

    if url.startswith('https://player.'):
        item['url'] = url
    elif '_audio' in item:
        paths = list(filter(None, urlsplit(url).path[1:].split('/')))
        path = '/' + paths[-2]
        x = paths[-1].split('_')
        y = item['author']['name'].split(' ')[0].lower()
        try:
            i = x.index(y)
            path += '/' + '_'.join(x[0:i])
            path += '/' + '_'.join(x[i:])
            paths = list(filter(None, urlsplit(item['_audio']).path[1:].split('/')))
            path += '/' + paths[-1].split('.')[0]
            item['url'] = 'https://player.amperwavepodcasting.com' + path
            # print(item['url'])
        except:
            logger.warning('unable to determine episode url')

    dt = dateutil.parser.parse(episode['published'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    if episode.get('tags'):
        item['tags'] = []
        for it in episode['tags']:
            if it['term'].lower() not in item['tags']:
                item['tags'].append(it['term'].lower())
    elif episode.get('media_keywords'):
        item['tags'] = episode['media_keywords'].split(',')

    if episode.get('image'):
        item['image'] = episode['image']['href']
    elif episode.get('media_thumbnail'):
        item['image'] = episode['media_thumbnail'][0]['href']

    if episode.get('summary'):
        item['summary'] = episode['summary']

    item['content_html'] = utils.add_audio(item.get('_audio'), item['image'], item['title'], item['url'], item['author']['name'], '', item['_display_date'], episode['itunes_duration'].lstrip('0:'))
    if 'embed' not in args and 'summary' in item:
        item['content_html'] += item['summary']

    return item


def get_feed(url, args, site_json, save_debug=False):
    if not url.startswith('https://rss.'):
        logger.warning('unhandled feed url ' + url)
        return None

    feed_html = utils.get_url_html(url)
    if not feed_html:
        return None
    try:
        podcast_feed = feedparser.parse(feed_html)
    except:
        logger.warning('Feedparser error ' + url)
        return None

    if save_debug:
        utils.write_file(podcast_feed, './debug/feed.json')

    feed = utils.init_jsonfeed(args)
    if 'title' in podcast_feed['feed']:
        feed['title'] = podcast_feed['feed']['title']

    n = 0
    feed_items = []
    for episode in podcast_feed['entries']:
        item = add_episode(episode, podcast_feed, url, args)
        if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
