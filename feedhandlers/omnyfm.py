import math, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # https://omny.fm/shows/blindsided/03-paul-bissonnette/embed
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] != 'shows':
        logger.warning('unhandled url ' + url)

    m = re.search(r'\/shows\/([^\/]+)\/([^\/]+)', url)
    if not m:
        logger.warning('unhandled url ' + url)
        return None

    item = {}

    if m.group(2) == 'playlists':
        api_url = 'https://omny.fm/api/embed/shows/{}/playlist/{}'.format(paths[1], paths[3])
        audio_json = utils.get_url_json(api_url)
        if not audio_json:
            return None
        if save_debug:
            utils.write_file(audio_json, './debug/audio.json')

        item['id'] = audio_json['Program']['Id']
        item['url'] = audio_json['PlaylistPageUrl']
        item['title'] = audio_json['Program']['Name']
        dt = datetime.fromisoformat(re.sub('\.\d+Z$', '+00:00', audio_json['Clips'][0]['PublishedUtc']))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        item['author'] = {"name": audio_json['Program']['Name']}
        item['_image'] = audio_json['Images']['Small']
        item['summary'] = audio_json['Program']['Description']
        poster = item['_image']
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>{}</small>'.format(item['url'], item['title'], item['summary'])
        item['content_html'] = '<table style="width:100%"><tr><td><a href="{}"><img width="128px" src="{}"/></a></td><td>{}</td></tr></table><table style="width:95%; margin-left:auto;">'.format(item['url'], poster, desc)
        if 'embed' in args:
            n = 5
        else:
            n = -1
        for i, clip in enumerate(audio_json['Clips']):
            if i == n:
                break
            poster = '{}/static/play_button-48x48.png'.format(config.server)
            duration = []
            t = math.floor(float(clip['DurationMilliseconds']) / 3600000)
            if t >= 1:
                duration.append('{} hr'.format(t))
            t = math.ceil((float(clip['DurationMilliseconds']) - 3600000 * t) / 60000)
            if t > 0:
                duration.append('{} min.'.format(t))
            dt = datetime.fromisoformat(re.sub('\.\d+Z$', '+00:00', clip['PublishedUtc']))
            desc = '<small><strong><a href="{}">{}</a></strong><br/>{}. {} · {}</small>'.format(clip['OmnyShareUrl'], clip['Title'], dt.strftime('%b'), dt.day, ', '.join(duration))
            item['content_html'] += '<tr><td><a href="{}"><img src="{}"/></a></td><td>{}</td></tr>'.format(clip['AudioUrl'], poster, desc)
        item['content_html'] += '</table>'
    else:
        api_url = 'https://omny.fm/api/embed/shows/{}/clip/{}'.format(paths[1], paths[2])
        audio_json = utils.get_url_json(api_url)
        if not audio_json:
            return None
        if save_debug:
            utils.write_file(audio_json, './debug/audio.json')

        item['id'] = audio_json['Id']
        item['url'] = audio_json['OmnyShareUrl']
        item['title'] = audio_json['Title']

        dt = datetime.fromisoformat(re.sub('\.\d+Z$', '+00:00', audio_json['PublishedUtc']))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        item['author'] = {"name": audio_json['Porgram']['Name']}
        item['_image'] = audio_json['Images']['Small']
        item['_audio'] = utils.get_redirect_url(audio_json['AudioUrl'])
        item['summary'] = audio_json['DescriptionHtml']

        duration = []
        t = math.floor(float(audio_json['DurationMilliseconds']) / 3600000)
        if t >= 1:
            duration.append('{} hr'.format(t))
        t = math.ceil((float(audio_json['DurationMilliseconds']) - 3600000 * t) / 60000)
        if t > 0:
            duration.append('{} min.'.format(t))

        poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="{}">{}</a><br/>{}</small>'.format(item['url'], item['title'], audio_json['Program']['ShowPageUrl'], item['author']['name'], ', '.join(duration))
        item['content_html'] = '<table style="width:100%"><tr><td><a href="{}"><img width="128px" src="{}"/></a></td><td>{}</td></table>'.format(item['_audio'], poster, desc)
        if not 'embed' in args:
            item['content_html'] += '<blockquote><small>{}</small></blockquote>'.format(item['summary'])
        item['content_html'] += '</div>'
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
