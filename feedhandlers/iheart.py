import json, math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
  clean_url = utils.clean_url(url)
  page_html = utils.get_url_html(clean_url)
  soup = BeautifulSoup(page_html, 'html.parser')
  data = soup.find('script', id='initialState')
  if not data:
    return None
  initial_state = json.loads(data.string)
  if save_debug:
    utils.write_file(initial_state, './debug/debug.json')

  item = {}
  if '/podcast/' in url:
    m = re.search(r'-(\d+)$', initial_state['routing']['params']['slugifiedId'])
    show_id = m.group(1)
    show = initial_state['podcast']['shows'][show_id]

    m = re.search(r'-(\d+)$', initial_state['routing']['params']['episodeSlug'])
    if not m:
      return None
    episode_id = m.group(1)
    episode = initial_state['podcast']['episodes'][episode_id]

    item['id'] = episode_id
    item['url'] = 'https://www.iheart.com' + show['url'] + episode['podcastSlug']
    item['title'] = episode['title']

    dt = datetime.fromtimestamp(episode['startDate']/1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

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

    poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="https://www.iheart.com{}">{}</a><br/>{}</small>'.format(item['url'], item['title'], show['url'], item['author']['name'], ', '.join(duration))
    item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;">&nbsp;</div>'.format(item['_audio'], poster, desc)
    if not 'embed' in args:
      item['content_html'] += item['summary']
    item['content_html'] += '</div>'

  return item
