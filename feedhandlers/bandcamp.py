import json
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if '/EmbeddedPlayer/' in url:
        embed_url = url
    else:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('meta', attrs={"property": "og:video"})
        if not el:
            logger.warning('unable to find the EmbeddedPlayer url in ' + url)
            return None
        embed_url = el['content']

    embed_html = utils.get_url_html(embed_url)
    if not embed_html:
        return None

    soup = BeautifulSoup(embed_html, 'lxml')
    el = soup.find('script', attrs={"data-player-data": True})
    if not el:
        logger.warning('unable to find data-player-data in ' + embed_url)
        return None

    bc_json = json.loads(unquote_plus(el['data-player-data']))

    item = {}
    if '/track=' in embed_url:
        if save_debug:
            utils.write_file(bc_json, './debug/bc-track.json')

        # if bc_json.get('album_id'):
        #     album_item = get_content('https://bandcamp.com/EmbeddedPlayer/v=2/album={}/size=large/tracklist=false/artwork=small/'.format(bc_json['album_id']), args, site_json, save_debug)
        # else:
        #     album_item = None

        track = bc_json['tracks'][0]
        item['id'] = track['id']
        item['url'] = track['title_link']
        item['title'] = track['title']

        if bc_json.get('publish_date'):
            dt = dateutil.parser.parse(bc_json['publish_date'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {
            "name": track['artist']
        }
        if bc_json.get('band_url'):
            item['author']['url'] = bc_json['band_url']
        item['authors'] = []
        item['authors'].append(item['author'])

        if track.get('art'):
            item['image'] = track['art']
        else:
            item['image'] = bc_json['album_art']

        if track.get('file'):
            for key, val in track['file'].items():
                if 'mp3' in key:
                    item['_audio'] = val
                    attachment = {}
                    attachment['url'] = item['_audio']
                    attachment['mime_type'] = 'audio/mpeg'
                    item['attachments'] = []
                    item['attachments'].append(attachment)
                    break

        item['content_html'] = utils.add_audio(item['url'], item['image'], item['title'], item['url'], item['author']['name'], item['author'].get('url'), '', utils.calc_duration(track['duration'], True, ':'), audio_type='audio_redirect')

    elif '/album=' in embed_url:
        if save_debug:
            utils.write_file(bc_json, './debug/bc-album.json')
        item['id'] = bc_json['album_id']
        item['url'] = bc_json['linkback']
        item['title'] = bc_json['album_title']

        if bc_json.get('packages'):
            package = next((it for it in bc_json['packages'] if 'album_id' in it and it['album_id'] == bc_json['album_id']), None)
            if package and package.get('album_release_date'):
                dt = dateutil.parser.parse(package['album_release_date'])
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt, False)
        if 'date_published' not in item and bc_json.get('featured_track_id'):
            track_item = get_content('https://bandcamp.com/EmbeddedPlayer/v=2/track={}/size=large/tracklist=false/artwork=small/'.format(bc_json['featured_track_id']), args, site_json, save_debug)
            if track_item:
                item['date_published'] = track_item['date_published']
                item['_timestamp'] = track_item['_timestamp']
                item['_display_date'] = track_item['_display_date']
        if 'date_published' not in item:
            dt = dateutil.parser.parse(bc_json['publish_date'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {
            "name": bc_json['artist']
        }
        if bc_json.get('band_url'):
            item['author']['url'] = bc_json['band_url']
        # for track in bc_json['tracks']:
        #     if track['artist'] != bc_json['artist']:
        #         item['author'] = {
        #             "name": "Various Artists"
        #         }
        #         break

        item['image'] = bc_json['album_art']

        tracks_html = ''
        if bc_json.get('tracks'):
            item['_playlist'] = []
            tracks_html += '<h3>Tracks:</h3>'
            for i, track in enumerate(bc_json['tracks'], 1):
                title = '{}. {}'.format(i, track['title'])
                if track['artist'] != bc_json['artist']:
                    title += ' (' + track['artist'] + ')'
                if track['track_streaming'] == True:
                    tracks_html += utils.add_audio(track['title_link'], item['image'], title, track['title_link'], '', '', '', utils.calc_duration(track['duration'], True, ':'), audio_type='audio_redirect', show_poster=False)
                    if track.get('file'):
                        for key, val in track['file'].items():
                            if 'mp3' in key:
                                item['_playlist'].append({
                                    "src": val,
                                    "name": '{}. {}'.format(i, track['title']),
                                    "artist": track['artist'],
                                    "image": item['image']
                                })
                                break
                else:
                    tracks_html += utils.add_audio('', '', title, track['title_link'], '', '', '', utils.calc_duration(track['duration'], True, ':'))

        item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
        item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;">'
        if item.get('_playlist'):
            item['content_html'] += '<a href="{}/playlist?url={}" target="_blank"><img src="{}/image?url={}&width=160&overlay=audio" style="width:100%;"/></a></div>'.format(config.server, quote_plus(item['url']), config.server, quote_plus(item['image']))
        else:
            item['content_html'] += '<a href="{}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(item['url'], item['image'])
        item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
        if 'url' in item['author']:
            item['content_html'] += '<div style="margin:4px 0 4px 0;"><a href="{}">{}</a></div>'.format(item['author']['url'], item['author']['name'])
        else:
            item['content_html'] += '<div style="margin:4px 0 4px 0;">{}</div>'.format(item['author']['name'])
        item['content_html'] += '<div style="margin:4px 0 4px 0;">Released: {}</div>'.format(item['_display_date'])
        item['content_html'] += '</div></div>' + tracks_html

    return item


def get_feed(url, args, site_json, save_debug):
    return None
