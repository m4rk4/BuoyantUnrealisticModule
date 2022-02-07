import math, pytz, re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_episode(episode, show):
    item = {}
    item['id'] = episode['id']
    item['url'] = 'https://www.iheart.com/podcast/{}-{}/episode/{}/'.format(show['slug'], show['id'], episode['id'])
    item['title'] = episode['title']

    dt = datetime.fromtimestamp(episode['startDate'] / 1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    dt_loc = dt.astimezone(pytz.timezone(config.local_tz))
    item['_display_date'] = '{}. {}, {}'.format(dt_loc.strftime('%b'), dt_loc.day, dt_loc.year)

    item['author'] = {}
    item['author']['name'] = show['title']

    item['_image'] = episode['imageUrl']
    item['_audio'] = utils.get_redirect_url(episode['mediaUrl'])
    item['summary'] = episode['description']

    duration = []
    t = math.floor(float(episode['duration']) / 3600)
    if t >= 1:
        duration.append('{} hr'.format(t))
    t = math.ceil((float(episode['duration']) - 3600 * t) / 60)
    if t > 0:
        duration.append('{} min.'.format(t))
    item['_duration'] = ', '.join(duration)
    return item


def get_content(url, args, save_debug=False):
    clean_url = utils.clean_url(url)
    show = None
    m = re.search(r'/podcast/[^/]+-(\d+)', clean_url)
    if m:
        show = utils.get_url_json('https://us.api.iheart.com/api/v3/podcast/podcasts/' + m.group(1))
        if save_debug:
            utils.write_file(show, './debug/podcast.json')

    episode = None
    m = re.search(r'/episode/[^/]+-(\d+)', clean_url)
    if m:
        episode = utils.get_url_json('https://us.api.iheart.com/api/v3/podcast/episodes/' + m.group(1))
        if save_debug:
            utils.write_file(show, './debug/iheart.json')

    if episode and show:
        item = get_episode(episode['episode'], show)
        show_url = 'https://www.iheart.com/podcast/{}-{}/'.format(show['slug'], show['id'])
        poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="https://www.iheart.com{}">{}</a><br/>{} &#8226; {}</small>'.format(item['url'], item['title'], show_url, item['author']['name'], item['_display_date'], item['_duration'])
        item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(item['_audio'], poster, desc)
        if not 'embed' in args:
            item['content_html'] += '<blockquote style="border-left:3px solid #ccc; margin-top:4px; margin-left:1.5em; padding-left:0.5em;"><small>{}</small></blockquote>'.format(item['summary'])

    elif show and not episode:
        item = {}
        item['id'] = show['id']
        item['url'] = 'https://www.iheart.com/podcast/{}-{}/'.format(show['slug'], show['id'])
        item['title'] = show['title']

        item['author'] = {}
        item['author']['name'] = show['title']

        item['_image'] = show['imageUrl']
        item['summary'] = show['description']

        poster = '{}/image?url={}&height=128'.format(config.server, quote_plus(item['_image']))
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4>'.format(item['url'], item['title'])
        item['content_html'] = '<div><img style="float:left; margin-right:8px;" src="{}"/><div>{}</div><div style="clear:left;"></div></div>'.format(poster, desc)

        item['content_html'] += '<blockquote style="border-left:3px solid #ccc; margin-top:4px; margin-left:1.5em; padding-left:0.5em;"><h4 style="margin-top:0; margin-bottom:1em;">Episodes:</h4>'
        episodes = utils.get_url_json('https://us.api.iheart.com/api/v3/podcast/podcasts/{}/episodes?newEnabled=false&limit=5&sortBy=startDate-desc'.format(show['id']))
        ts = []
        if 'embed' in args:
            n = 5
        else:
            n = 10
        for i, ep in enumerate(episodes['data']):
            if i == n:
                break
            episode = utils.get_url_json('https://us.api.iheart.com/api/v3/podcast/episodes/{}'.format(ep['id']))
            episode_item = get_episode(episode['episode'], show)
            ts.append(episode_item['_timestamp'])
            poster = '{}/static/play_button-48x48.png'.format(config.server)
            desc = '<h5 style="margin-top:0; margin-bottom:0;"><a href="{}">{}</a></h5><small>{} &#8226; {}</small>'.format(episode_item['url'], episode_item['title'], episode_item['_display_date'], episode_item['_duration'])
            item['content_html'] += '<div style="margin-bottom:1em;"><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(episode_item['_audio'], poster, desc)
        item['content_html'] += '</blockquote>'
        if not 'embed' in args:
            item['content_html'] += '<div>{}</div>'.format(item['summary'].replace('\n', '<br/>'))

        dt = datetime.fromtimestamp(max(ts))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        dt_loc = dt.astimezone(pytz.timezone(config.local_tz))
        item['_display_date'] = '{}. {}, {}'.format(dt_loc.strftime('%b'), dt_loc.day, dt_loc.year)

    else:
        logger.warning('unsupported url ' + url)
        return None

    return item
