import pytz, re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

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
    item['_display_date'] = utils.format_display_date(dt_loc, False)

    item['author'] = {
        "name": show['title']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['image'] = episode['imageUrl']
    item['_audio'] = utils.find_redirect_url(episode['mediaUrl'])
    item['summary'] = episode['description']
    item['_duration'] = utils.calc_duration(float(episode['duration']))
    return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    show = None
    if 'podcast' in paths:
        m = re.search(r'\d+$', paths[paths.index('podcast') + 1])
        if m:
            show = utils.get_url_json('https://us.api.iheart.com/api/v3/podcast/podcasts/' + m.group(0))
            if save_debug:
                utils.write_file(show, './debug/podcast.json')

    episode = None
    if 'episode' in paths:
        m = re.search(r'\d+$', paths[paths.index('episode') + 1])
        if m:
            episode = utils.get_url_json('https://us.api.iheart.com/api/v3/podcast/episodes/' + m.group(0))
            if save_debug:
                utils.write_file(show, './debug/episode.json')

    if episode and show:
        item = get_episode(episode['episode'], show)
        show_url = 'https://www.iheart.com/podcast/{}-{}/'.format(show['slug'], show['id'])
        if 'embed' not in args and 'summary' in item:
            desc = '<p><small>' + item['summary'] + '</small></p>'
        else:
            desc = ''
        item['content_html'] = utils.add_audio_v2(item['_audio'], item.get('image'), item['title'], item['url'], item['author']['name'], show_url, item['_display_date'], item['_duration'], desc=desc)

    elif show and not episode:
        item = {}
        item['id'] = show['id']
        item['url'] = 'https://www.iheart.com/podcast/{}-{}/'.format(show['slug'], show['id'])
        item['title'] = show['title']

        item['author'] = {
            "name": show['title']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['image'] = show['imageUrl']
        card_image = '<a href="{}" target="_blank"><div style="width:100%; height:100%; background:url(\'{}\'); background-position:center; background-size:cover; border-radius:10px 0 0 0;"></div></a>'.format(item['url'], item['image'])

        card_content = '<div style="padding-left:8px; font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])

        if show.get('description'):
            item['summary'] = show['description'].replace('\n', '<br/>')
            card_content += '<div style="padding-left:8px; margin-top:0.5em; font-size:0.9em; overflow:hidden; display:-webkit-box; -webkit-line-clamp:3; line-clamp:3; -webkit-box-orient:vertical;">' + item['summary'] + '</div>'

        card_footer = '<h3>Episodes:</h3>'
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
            card_footer += utils.add_audio_v2(episode_item['_audio'], '', episode_item['title'], episode_item['url'], '', '', episode_item['_display_date'], episode_item['_duration'], show_poster=False, border=False, margin="0 auto")
    
        item['content_html'] = utils.format_small_card(card_image, card_content, card_footer)

        dt = datetime.fromtimestamp(max(ts))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        dt_loc = dt.astimezone(pytz.timezone(config.local_tz))
        item['_display_date'] = '{}. {}, {}'.format(dt_loc.strftime('%b'), dt_loc.day, dt_loc.year)

    else:
        logger.warning('unsupported url ' + url)
        return None

    return item
