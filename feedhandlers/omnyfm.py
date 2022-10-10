import math, re, tldextract
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_build_id(url):
    page_html = utils.get_url_html(url)
    m = re.search(r'"buildId":"([^"]+)"', page_html)
    if not m:
        return ''
    return m.group(1)


def calc_duration(seconds):
    duration = []
    t = math.floor(float(seconds) / 3600)
    if t >= 1:
        duration.append('{} hr'.format(t))
    t = math.ceil((float(seconds) - 3600 * t) / 60)
    if t > 0:
        duration.append('{} min.'.format(t))
    return ', '.join(duration)


def get_next_json(url):
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        path += '.json'
    else:
        path = '/index.json'

    tld = tldextract.extract(url)
    sites_json = utils.read_json_file('./sites.json')
    build_id = sites_json[tld.domain]['buildId']

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, build_id, path)
    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        # Try updating the build id
        logger.debug('updating buildId for ' + url)
        new_build_id = get_build_id(url)
        if new_build_id != build_id:
            sites_json[tld.domain]['buildId'] = new_build_id
            utils.write_file(sites_json, './sites.json')
            next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, new_build_id, path)
            next_json = utils.get_url_json(next_url, retries=1)
    return next_json


def get_content(url, args, save_debug=False):
    # https://omny.fm/shows/blindsided/03-paul-bissonnette/embed
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] != 'shows':
        logger.warning('unhandled url ' + url)
        return None

    page_url = re.sub(r'/embed', '', url)
    next_json = get_next_json(page_url)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    item = {}
    if next_json['pageProps'].get('clip'):
        clip_json = next_json['pageProps']['clip']
        item['id'] = clip_json['Id']
        item['url'] = clip_json['PublishedUrl']
        item['title'] = clip_json['Title']

        date = clip_json['PublishedUtc']
        m = re.search(r'\.(\d{1,2})Z$', date)
        if m:
            date = date.replace(m.group(0), '.{}Z'.format(m.group(1).zfill(3)))
        dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        date = clip_json['ModifiedAtUtc']
        m = re.search(r'\.(\d{1,2})Z$', date)
        if m:
            date = date.replace(m.group(0), '.{}Z'.format(m.group(1).zfill(3)))
        dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

        item['author'] = {}
        item['author']['name'] = clip_json['Program']['Name']
        item['author']['url'] = 'https://omny.fm/shows/' + clip_json['Program']['Slug']

        if clip_json.get('Tags'):
            item['tags'] = clip_json['Tags'].copy()

        item['_image'] = clip_json['ImageUrl']

        item['_audio'] = clip_json['AudioUrl']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['summary'] = clip_json['Description']

        duration = calc_duration(clip_json['DurationSeconds'])

        poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(item['_image']))

        item['content_html'] = '<table style="width:100%;"><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;" /></a></td><td style="vertical-align:top;"><a href="{}"><span style="font-size:1.1em; font-weight:bold;">{}</span></a><br/>by <a href="{}">{}</a><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(item['_audio'], poster, item['url'], item['title'], item['author']['url'], item['author']['name'], item['_display_date'], duration)

        if 'embed' not in args:
            item['content_html'] += clip_json['DescriptionHtml']

    elif next_json['pageProps'].get('program'):
        program_json = next_json['pageProps']['program']
        item['id'] = program_json['Id']
        item['url'] = 'https://omny.fm/shows/' + program_json['Slug']
        item['title'] = program_json['Name']

        date = program_json['ModifiedAtUtc']
        m = re.search(r'\.(\d{1,2})Z$', date)
        if m:
            date = date.replace(m.group(0), '.{}Z'.format(m.group(1).zfill(3)))
        dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {
            "name": item['title'],
            "url": item['url']
        }

        item['tags'] = program_json['Categories'].copy()
        item['_image'] = program_json['ArtworkUrl']
        item['summary'] = program_json['Description']

        item['content_html'] = '<table style="width:100%;"><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;" /></a></td><td style="vertical-align:top;"><a href="{}"><span style="font-size:1.1em; font-weight:bold;">{}</span></a></td></tr></table>'.format(item['url'], item['_image'], item['url'], item['title'])

        if 'embed' not in args:
            item['content_html'] += program_json['DescriptionHtml']
            n = 1000
        else:
            n = 5

        item['content_html'] += '<table>'
        for clip in next_json['pageProps']['playlistsWithClips'][0]['clips']:
            date = clip['PublishedUtc']
            m = re.search(r'\.(\d{1,2})Z$', date)
            if m:
                date = date.replace(m.group(0), '.{}Z'.format(m.group(1).zfill(3)))
            dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
            display_date = utils.format_display_date(dt, False)
            duration = calc_duration(clip['DurationSeconds'])
            item['content_html'] += '<tr><td><a href="{}"><img src="{}/static/play_button-48x48.png"/></a></td><td><a href="{}">{}</a><br><small>{}&nbsp;&bull;&nbsp;{}</td></tr>'.format(clip['AudioUrl'], config.server, clip['PublishedUrl'], clip['Title'], display_date, duration)
        item['content_html'] += '</table>'
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
