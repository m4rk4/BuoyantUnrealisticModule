import json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # Only configured for episode embeds
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Not(A:Brand\";v=\"8\", \"Chromium\";v=\"144\", \"Microsoft Edge\";v=\"144\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }

    split_url = urlsplit(url.strip())
    description = ''

    if split_url.netloc != 'www.podbean.com':
        # https://bannerravens.podbean.com/
        page_html = utils.get_url_html(split_url.scheme + '://' + split_url.netloc)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find('script', string=re.compile(r'__INITIAL_STATE__'))
        if el:
            i = el.string.find('{')
            j = el.string.rfind('}') + 1
            utils.write_file(el.string[i:j], './debug/debug.txt')
            initial_state = json.loads(el.string[i:j].replace('\\\\\\"', '&QUOT;').replace('\\"', '"'))
            if save_debug:
                utils.write_file(initial_state, './debug/debug.json')
            if split_url.path.startswith('/e/'):
                # Episode
                episode = next((it for it in initial_state['store']['listEpisodes'] if it['permalink'].strip('/') == split_url.path.strip('/')), None)
                if episode:
                    split_url = urlsplit(episode['downloadLink'])
            else:
                # Show
                paths = list(filter(None, urlsplit(initial_state['store']['baseInfo']['podcastDeepLink']).path.split('/')))
                i = re.sub(r'([^-]+)-(.*)', r'\2-\1', paths[-1].replace('-playlist', ''))
                split_url = urlsplit('https://www.podbean.com/player-v2/?i=' + i + '-playlist')
                el = soup.find(class_='p-description')
                if el:
                    description = '<p>' + el.decode_contents() + '</p>'

    elif split_url.path.startswith('/podcast-detail/') or split_url.path.startswith('/itunes/'):
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find(id='share_link_input')
        if el:
            paths = list(filter(None, urlsplit(el['value']).path.split('/')))
            i = re.sub(r'([^-]+)-(.*)', r'\2-\1', paths[-1])
            split_url = urlsplit('https://www.podbean.com/player-v2/?i=' + i + '-playlist')
            el = soup.find(id='short_desc')
            if el:
                description = '<p>' + el.decode_contents() + '</p>'

    id = ''
    if split_url.path.startswith('/media/share/'):
        paths = list(filter(None, split_url.path.split('/')))
        id = re.sub(r'([^-]+)-(.*)', r'\2-\1', paths[-1])
        api_json = utils.get_url_json('https://www.podbean.com/player/' + id, headers=headers)
        if not api_json:
            return None
    elif split_url.path.startswith('/player-v2'):
        query = parse_qs(split_url.query)
        if not query.get('i'):
            logger.warning('unhandled podbean player url ' + url)
            return None
        id = query['i'][0]

    if not id:
        logger.warning('unknown id for ' + url)
        return None

    api_json = utils.get_url_json('https://www.podbean.com/player/' + id, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/podcast.json')

    item = {}
    if len(api_json['episodes']) == 1:
        episode = api_json['episodes'][0]
        item['id'] = episode['id']
        item['url'] = episode['link']
        item['title'] = episode['title']

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(episode['publishTime'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, date_only=True)

        item['author'] = {}
        if api_json['setting'].get('podcastTitle'):
            item['author']['name'] = api_json['setting']['podcastTitle']
        else:
            item['author']['name'] = api_json['setting']['author']
        if api_json['setting'].get('podcastLink'):
            item['author']['url'] = api_json['setting']['podcastLink']
        item['authors'] = []
        item['authors'].append(item['author'])

        if episode.get('largeLogo'):
            item['image'] = episode['largeLogo']

        if episode.get('content'):
            item['summary'] = episode['content']

        if episode.get('resource'):
            item['_audio'] = episode['resource']
            item['_audio_type'] = episode['resourceMimetype']
        elif episode.get('fallbackResource'):
            item['_audio'] = episode['fallbackResource']
            item['_audio_type'] = episode['fallbackResourceMimetype']
        elif episode.get('downloadLink'):
            item['_audio'] = episode['downloadLink']
            item['_audio_type'] = 'audio/mpeg'
        attachment = {
            "url": item['_audio'],
            "mime_type": item['_audio_type']
        }
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['_duration'] = episode['duration'].lstrip('0')
    else:
        item['id'] = id
        item['url'] = api_json['setting']['podcastLink']
        item['title'] = api_json['setting']['podcastTitle']

        episode = api_json['episodes'][0]
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(episode['publishTime'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, date_only=True)

        item['author'] = {
            "name": api_json['setting']['author']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        if episode.get('largeLogo'):
            item['image'] = episode['largeLogo']

        if description:
            item['summary'] = description

        item['_playlist'] = []
        item['_playlist_title'] = 'Episodes:'
        for episode in api_json['episodes']:
            track = {
                "title": episode['title'],
                "url": episode['link'],
                "image": item['image'],
                "duration": episode['duration'].lstrip('0')
            }
            if episode.get('resource'):
                track['src'] = episode['resource']
                track['mime_type'] = episode['resourceMimetype']
            elif episode.get('fallbackResource'):
                track['src'] = episode['fallbackResource']
                track['mime_type'] = episode['fallbackResourceMimetype']
            elif episode.get('downloadLink'):
                track['src'] = episode['downloadLink']
                track['mime_type'] = 'audio/mpeg'
            dt_loc = dateutil.parser.parse(episode['publishTime'])
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            track['date'] = utils.format_display_date(dt, date_only=True)
            item['_playlist'].append(track)

    item['content_html'] = utils.format_audio_content(item, logo=config.logo_podbean)
    if 'embed' not in args and 'summary' in item:
        item['content_html'] += item['summary']

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
