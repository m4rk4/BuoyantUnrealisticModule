import podcastparser
import urllib.request
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://playlist.megaphone.fm/?e=ESP3970143369
    # https://playlist.megaphone.fm/?p=ADV8942553180
    # https://cms.megaphone.fm/channel/FOXM2059868704
    api_url = ''
    episode_id = ''
    playlist_id = ''
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'megaphone.link':
        episode_id = paths[0]
        api_url = 'https://player.megaphone.fm/playlist/episode/' + episode_id
    elif split_url.netloc == 'playlist.megaphone.fm':
        query = parse_qs(split_url.query)
        if query.get('p'):
            playlist_id = query['p'][0]
            api_url = 'https://player.megaphone.fm/playlist/' + playlist_id
        elif query.get('e'):
            episode_id = query['e'][0]
            api_url = 'https://player.megaphone.fm/playlist/episode/' + episode_id
    elif split_url.netloc == 'player.megaphone.fm' and len(paths) == 1:
        episode_id = paths[0]
        api_url = 'https://player.megaphone.fm/playlist/episode/' + episode_id
    elif split_url.netloc == 'cms.megaphone.fm' and paths[0] == 'channel':
        playlist_id = paths[1]
        query = parse_qs(split_url.query)
        if query.get('selected'):
            episode_id = query['selected'][0]
        api_url = 'https://player.megaphone.fm/playlist/' + playlist_id

    if not api_url:
        logger.warning('unhandled url ' + url)
        return None

    podcast_json = utils.get_url_json(api_url)
    if not podcast_json:
        return None
    if save_debug:
        utils.write_file(podcast_json, './debug/podcast.json')

    # Sort episides, newest first
    episodes = sorted(podcast_json['episodes'], key=lambda x: datetime.fromisoformat(x['pubDate']), reverse=True)
    if episode_id:
        episode = next((it for it in episodes if it['uid'] == episode_id), None)
    else:
        episode = episodes[0]

    podcast_feed = None
    if podcast_json.get('podcastFeedUrl'):
        try:
            podcast_feed = podcastparser.parse(podcast_json['podcastFeedUrl'], urllib.request.urlopen(podcast_json['podcastFeedUrl']))
        except:
            pass

    item = {}
    if episode_id:
        item['id'] = episode['uid']
        item['url'] = 'https://playlist.megaphone.fm/?e=' + episode['uid']
        item['title'] = episode['title']
        if episode.get('subtitle'):
            item['title'] += ': ' + episode['subtitle']
        item['author'] = {
            "name": podcast_json['podcastTitle']
        }
        if podcast_feed:
            if podcast_feed.get('itunes_author'):
                item['author']['name'] += ' | ' + podcast_feed['itunes_author']
            if podcast_feed.get('link'):
                item['author']['url'] = podcast_feed['link']
    else:
        item['id'] = playlist_id
        item['url'] = 'https://playlist.megaphone.fm/?p=' + playlist_id
        item['title'] = podcast_json['podcastTitle']
        if podcast_feed and podcast_feed.get('itunes_author'):
            item['author'] = {
                "name": podcast_feed['itunes_author']
            }
            if podcast_feed.get('link'):
                item['author']['url'] = podcast_feed['link']
        else:
            item['author']['name'] = item['title']

    if 'author' in item:
        item['authors'] = []
        item['authors'].append(item['author'])

    dt = datetime.fromisoformat(episode['pubDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['image'] = episode['imageUrl']

    if podcast_feed and podcast_feed.get('itunes_categories'):
        item['tags'] = []
        for it in podcast_feed['itunes_categories']:
            if isinstance(it, list):
                item['tags'] += [x for x in it]
            else:
                item['tags'].append(it)

    if episode_id:
        item['summary'] = episode['summary']
        item['_audio'] = episode['episodeUrlHRef']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] = utils.add_audio(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author'].get('url'), item['_display_date'], episode['duration'])
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += item['summary']
    elif playlist_id:
        if podcast_feed:
            if podcast_feed.get('cover_url'):
                item['image'] = podcast_feed['cover_url']
            if podcast_feed.get('description'):
                item['summary'] = podcast_feed['description']
        item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
        item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="{0}/playlist?url={1}" target="_blank"><img src="{0}/image?url={2}&width=160&overlay=audio" style="width:100%;"/></a></div>'.format(config.server, quote_plus(item['url']), quote_plus(item['image']))
        item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
        if item.get('author'):
            item['content_html'] += '<div style="margin:4px 0 4px 0;">'
            if item['author'].get('url'):
                item['content_html'] += '<a href="{}">{}</a>'.format(item['author']['url'], item['author']['name'])
            else:
                item['content_html'] += item['author']['name']
            item['content_html'] += '</div>'
        # if item.get('summary'):
        #     item['content_html'] += '<div style="margin:4px 0 4px 0; font-size:0.8em;">{}</div>'.format(item['summary'])
        item['content_html'] += '</div></div>'
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += item['summary']

    if playlist_id:
        item['_playlist'] = []
        item['content_html'] += '<h3>Episodes:</h3>'
        for episode in episodes[:5]:
            title = episode['title']
            if episode.get('subtitle'):
                title += ': ' + episode['subtitle']
            dt = datetime.fromisoformat(episode['pubDate'])
            item['content_html'] += utils.add_audio(episode['episodeUrlHRef'], episode['imageUrl'], title, 'https://playlist.megaphone.fm/?e=' + episode['uid'], '', '', utils.format_display_date(dt, False), episode['duration'], show_poster=False)
            item['_playlist'].append({
                "src": episode['episodeUrlHRef'],
                "name": title,
                "artist": item['author']['name'],
                "image": episode['imageUrl']
            })

    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
