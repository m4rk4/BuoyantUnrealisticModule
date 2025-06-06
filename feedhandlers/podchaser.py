import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_creator(creator_id):
    return utils.get_url_json('https://api.podchaser.com/creators/{}/'.format(creator_id))


def get_podcast_episodes(podcast_id, n=5):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referrer": "https://www.podchaser.com/"
    }
    data = {
        "start": 0,
        "count": n,
        "sort_order":"SORT_ORDER_RECENT",
        "filters": {
            "podcast_id": podcast_id
        },
        "options": {},
        "omit_results": False,
        "total_hits": False
    }
    return utils.post_url('https://api.podchaser.com/list/episode', json_data=data, headers=headers)


def get_episode_content(ep_json, args):
    item = {}
    item['id'] = ep_json['guid']
    item['url'] = 'https://www.podchaser.com/podcasts/{}-{}/episodes/{}-{}'.format(ep_json['podcast']['slug'], ep_json['podcast']['id'], ep_json['slug'], ep_json['id'])
    item['title'] = ep_json['title']

    dt = datetime.fromisoformat(ep_json['air_date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, date_only=True)

    item['author'] = {
        "name": ep_json['podcast']['title'],
        "url": 'https://www.podchaser.com/podcasts/{}-{}'.format(ep_json['podcast']['slug'], ep_json['podcast']['id'])
    }
    item['authors'] = []
    item['authors'].append(item['author'].copy())
    if ep_json.get('creator_summary'):
        for it in ep_json['creator_summary']:
            if isinstance(it, dict):
                item['authors'].append({"name": it['name']})
            elif isinstance(it, int):
                creator = get_creator(it)
                if creator:
                    item['authors'].append({"name": creator['name']})
    if len(item['authors']) > 1:
        item['author']['name'] +=  ' (with ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors'][1:]])) + ')'

    item['tags'] = []
    if ep_json.get('hasttags'):
        logger.warning('unhandled episode hashtags in ' + item['url'])
        # item['tags'] += [x['text'] for x in ep_json['hashtags']]
    if ep_json['podcast'].get('categories'):
        item['tags'] += [x['text'] for x in ep_json['podcast']['categories']]

    if ep_json.get('image_url'):
        item['image'] = ep_json['image_url']
    elif ep_json['podcast'].get('image_url'):
        item['image'] = ep_json['podcast']['image_url']

    if ep_json.get('description'):
        item['summary'] = ep_json['description']

    item['_audio'] = ep_json['audio_url']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['content_html'] = utils.add_audio(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], ep_json['length'])
    if 'embed' not in args and 'summary' in item:
        item['content_html'] += item['summary']
    return item

def get_content(url, args, site_json, save_debug=False):
    # https://www.podchaser.com/podcasts/selected-shorts-57038/episodes/domestic-rearrangements-230841088
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    podcast_id = -1
    try:
        i = paths.index('podcasts') + 1
        if i > 0:
            m = re.search(r'\d+$', paths[i])
            if m:
                podcast_id = int(m.group(0))
    except:
        pass

    episode_id = -1
    try:
        i = paths.index('episodes') + 1
        if i > 0:
            m = re.search(r'\d+$', paths[i])
            if m:
                episode_id = int(m.group(0))
    except:
        pass

    # print(podcast_id, episode_id)

    if podcast_id > 0 and episode_id > 0:
        api_url = 'https://api.podchaser.com/podcasts/{}/episodes/{}/player_ids'.format(podcast_id, episode_id)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/podcast.json')
        return get_episode_content(api_json, args)

    elif podcast_id > 0:
        api_json = get_podcast_episodes(podcast_id, 5)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/podcast.json')

        podcast_json = api_json['additional_entities']['podcasts'][0]
        item = {}
        item['id'] = podcast_json['id']
        item['url'] = 'https://www.podchaser.com/podcasts/{}-{}'.format(podcast_json['slug'], podcast_json['id'])
        item['title'] = podcast_json['title']

        dt = datetime.fromisoformat(podcast_json['date_of_latest_episode']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, date_only=True)

        item['authors'] = [{"name": x['name']} for x in podcast_json['creator_summary'].values()]
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }

        if podcast_json.get('categories'):
            item['tags'] = [x['text'] for x in podcast_json['categories']]

        if podcast_json.get('image_url'):
            item['image'] = podcast_json['image_url']

        if podcast_json.get('description'):
            item['summary'] = podcast_json['description']

        item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
        item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="{0}/playlist?url={1}" target="_blank"><img src="{0}/image?url={2}&width=160&overlay=audio" style="width:100%;"/></a></div>'.format(config.server, quote_plus(item['url']), quote_plus(item['image']))
        item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
        item['content_html'] += '<div style="margin:4px 0 4px 0;">Hosted by {}</div>'.format(item['author']['name'])
        item['content_html'] += '</div></div>'
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += item['summary']

        item['_playlist'] = []
        item['content_html'] += '<h3>Episodes:</h3>'
        for episode in api_json['entities']:
            dt = datetime.fromisoformat(episode['air_date']).replace(tzinfo=timezone.utc)
            if episode.get('image_url'):
                poster = episode['image_url']
            else:
                poster = item['image']
            episode_url = item['url'] + '/episodes/{}-{}'.format(episode['slug'], episode['id'])
            item['content_html'] += utils.add_audio(episode['audio_url'], poster, episode['title'], episode_url, '', '', utils.format_display_date(dt, date_only=True), episode['length'], show_poster=False)
            item['_playlist'].append({
                "src": episode['audio_url'],
                "name": episode['title'],
                "artist": podcast_json['title'],
                "image": poster
            })            

    else:
        logger.warning('unknown podcast id and/or episode id in ' + url)
        return None

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    podcast_id = -1
    try:
        i = paths.index('podcasts') + 1
        if i > 0:
            m = re.search(r'\d+$', paths[i])
            if m:
                podcast_id = int(m.group(0))
    except:
        pass
    if podcast_id < 0:
        logger.warning('unable to determine podcast id in ' + url)
        return None

    api_json = get_podcast_episodes(podcast_id, 10)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/podcast.json')

    n = 0
    feed_items = []
    for episode in api_json['entities']:
        ep_url = 'https://www.podchaser.com/podcasts/{}-{}/episodes/{}-{}'.format(episode['podcast']['slug'], episode['podcast']['id'], episode['slug'], episode['id'])
        if save_debug:
            logger.debug('getting content for ' + ep_url)
        item = get_episode_content(episode, args)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['title'] = api_json['additional_entities']['podcasts'][0]['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
