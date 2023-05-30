import math
from bs4 import BeautifulSoup

import config, utils

import logging
logger = logging.getLogger(__name__)

def calc_duration(sec):
  duration = []
  t = math.floor(float(sec) / 3600)
  if t >= 1:
    duration.append('{} hr'.format(t))
  t = math.ceil((float(sec) - 3600 * t) / 60)
  if t > 0:
    duration.append('{} min.'.format(t))
  return duration

def get_content(url, args, site_json, save_debug=False):
    # TODO: incomplete
    # https://player.fireside.fm/v2/B6ASng9o+cA6r1-uy?theme=dark
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    share_url = 'https://share.fireside.fm/episode/{}'.format(paths[-1])
    page_html = utils.get_url_html(share_url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')

    item = {}
    item['id'] = paths[-1]
    item['url'] = share_url

    el = soup.find('meta', attrs={"property": "og:title"})
    item['title'] = el['content']

    el = soup.find('meta', attrs={"property": "og:site_name"})
    item['author'] = {"name": el['content']}

    el = soup.find('h1')


    el = soup.find('meta', attrs={"property": "og:image"})
    item['_image'] = el['content']

    el = soup.find('meta', attrs={"property": "og:audio:secure_url"})
    item['_audio'] = el['content']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    el = soup.find('meta', attrs={"name": "description"})
    item['summary'] = el['content']
