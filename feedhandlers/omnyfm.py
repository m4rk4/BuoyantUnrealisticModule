import re
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
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        #utils.write_file(page_html, './debug/debug.html')
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    # https://omny.fm/shows/blindsided/03-paul-bissonnette/embed
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] != 'shows':
        logger.warning('unhandled url ' + url)
        return None

    if 'embed' in paths:
        paths.remove('embed')
    page_url = 'https://' + split_url.netloc + '/' + '/'.join(paths)

    next_json = get_next_data(page_url, site_json)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/omny.json')

    item = {}
    if next_json['pageProps'].get('clip'):
        clip_json = next_json['pageProps']['clip']
        item['id'] = clip_json['Id']
        item['url'] = clip_json['PublishedUrl']
        item['title'] = clip_json['Title']
        dt = datetime.fromisoformat(clip_json['PublishedUtc'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)
        if clip_json.get('ModifiedAtUtc'):
            dt = datetime.fromisoformat(clip_json['ModifiedAtUtc'])
        item['date_modified'] = dt.isoformat()
        item['author'] = {
            "name": clip_json['Program']['Name'],
            "url": "https://omny.fm/shows/" + clip_json['Program']['Slug']
        }
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
        item['content_html'] = utils.add_audio(item['_audio'], item['_image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(clip_json['DurationSeconds']))
        if 'embed' not in args:
            item['content_html'] += clip_json['DescriptionHtml']

    elif next_json['pageProps'].get('program'):
        program_json = next_json['pageProps']['program']
        item['id'] = program_json['Id']
        item['url'] = 'https://omny.fm/shows/' + program_json['Slug']
        item['title'] = program_json['Name']
        dt = datetime.fromisoformat(program_json['ModifiedAtUtc'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)
        item['author'] = {
            "name": item['title'],
            "url": item['url']
        }
        if program_json.get('Categories'):
            item['tags'] = program_json['Categories'].copy()
        item['_image'] = program_json['ArtworkUrl']
        item['summary'] = program_json['DescriptionHtml']
        item['content_html'] = utils.add_audio('', item['_image'], item['title'], item['url'], '', '', '', '', desc=program_json.get('DescriptionHtml'))
        if 'embed' not in args:
            n = 1000
        else:
            n = 5
        item['content_html'] += '<h3 style="margin:8px;">Clips:</h3>'
        for i, clip in enumerate(next_json['pageProps']['clips']['Clips']):
            if i == n:
                break
            item['content_html'] += utils.add_audio(clip['AudioUrl'], clip['ImageUrl'], clip['Title'], clip['PublishedUrl'], '', '', utils.format_display_date(datetime.fromisoformat(clip['PublishedUtc']), False), clip['DurationSeconds'], show_poster=False)

    elif 'playlist' in next_json['pageProps']:
        playlist_json = next_json['pageProps']['playlist']
        item['id'] = playlist_json['Id']
        item['url'] = 'https://omny.fm/shows/' + playlist_json['ProgramSlug'] + '/' + playlist_json['Slug']
        item['title'] = playlist_json['Title']
        dt = datetime.fromisoformat(playlist_json['ModifiedAtUtc'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)
        item['author'] = {
            "name": playlist_json['Author'],
            "url": "https://omny.fm/shows/" + playlist_json['ProgramSlug']
        }
        if playlist_json.get('Categories'):
            item['tags'] = playlist_json['Categories'].copy()
        item['_image'] = playlist_json['ArtworkUrl']
        item['content_html'] = utils.add_audio('', item['_image'], item['title'], item['url'], item['author']['name'], item['author']['url'], '', '', desc=playlist_json.get('DescriptionHtml'))
        if 'embed' not in args:
            n = 1000
        else:
            n = 5
        item['content_html'] += '<h3 style="margin:8px;">Clips:</h3>'
        for i, clip in enumerate(next_json['pageProps']['playlistPage']['Clips']):
            if i == n:
                break
            item['content_html'] += utils.add_audio(clip['AudioUrl'], clip['ImageUrl'], clip['Title'], clip['PublishedUrl'], '', '', utils.format_display_date(datetime.fromisoformat(clip['PublishedUtc']), False), clip['DurationSeconds'], show_poster=False)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
