import math, re, requests
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_token(url):
  js = utils.get_url_html('https://js-cdn.music.apple.com/musickit/v2/components/musickit-components/musickit-components.esm.js')
  if not js:
    return ''

  m = re.search(r'JSON\.parse\(\'\[\["([^"]+)"', js)
  if not m:
    return ''

  js = utils.get_url_html('https://js-cdn.music.apple.com/musickit/v2/components/musickit-components/{}.entry.js'.format(m.group(1)))
  if not js:
    return ''

  jsfiles = re.findall(r'(from|import)"\.\/(p-[0-9a-f]+\.js)"', js)
  for jsfile in jsfiles:
    js = utils.get_url_html('https://js-cdn.music.apple.com/musickit/v2/components/musickit-components/{}'.format(jsfile[1]))
    if not js:
      continue
    m = re.search('podcasts:\{prod:"([^"]+)"', js)
    if m:
      return m.group(1)

  return ''

def get_apple_data(api_url, url, save_debug=False):
  s = requests.Session()
  headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "access-control-request-headers": "authorization",
    "access-control-request-method": "GET",
    "cache-control": "no-cache",
    "dnt": "1",
    "origin": "https://embed.podcasts.apple.com",
    "pragma": "no-cache",
    "referer": "https://embed.podcasts.apple.com/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36"
  }
  preflight = s.options(api_url, headers=headers)
  if preflight.status_code != 204:
    logger.warning('unexpected status code {} getting preflight info from {}'.format(preflight.status_code, url))
    return ''

  headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Bearer eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IkRBSlcxUk8wNjIifQ.eyJpc3MiOiJFUk1UQTBBQjZNIiwiaWF0IjoxNjMzNDUzNzU2LCJleHAiOjE2Mzk2NzQ1NTYsIm9yaWdpbiI6WyJodHRwczovL2VtYmVkLnBvZGNhc3RzLmFwcGxlLmNvbSJdfQ.qlGFbohnsbm6faxvdKrr1yF5_n4Ni09UkJcXOYaWLZeF7ogVJGhSVCxocP975k3fQpTSfCt5aU8SN5ooi8syzQ",
    "cache-control": "no-cache",
    "dnt": "1",
    "origin": "https://embed.podcasts.apple.com",
    "pragma": "no-cache",
    "referer": "https://embed.podcasts.apple.com/",
    "sec-ch-ua": "\"Chromium\";v=\"92\", \" Not A;Brand\";v=\"99\", \"Google Chrome\";v=\"92\"",
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36"
  }
  r = s.get(api_url, headers=headers)
  if r.status_code != 200:
    # The token might be expired, try to get a new one
    token = get_token(url)
    if token:
      logger.debug('trying new Apple token to ' + token)
      headers['authorization'] = 'Bearer ' + token
      r = s.get(api_url, headers=headers)
  if r.status_code != 200:
    logger.warning('unexpected status code {} getting request info from {}'.format(r.status_code, url))
    return ''

  return r.json()

def get_apple_playlist(url, args, save_debug=False):
  api_url = ''
  if '/podcast/' in url:
    m = re.search(r'\/id(\d+)', url)
    if m:
      api_url = 'https://amp-api.podcasts.apple.com/v1/catalog/us/podcasts/{}?include=episodes'.format(m.group(1))
  elif '/playlist/' in url:
    m = re.search(r'\/pl\.([0-9a-f]+)', url)
    if m:
      api_url = 'https://api.music.apple.com/v1/catalog/us/playlists?ids=pl.{}&include=curator'.format(m.group(1))
  elif '/album/' in url:
    m = re.search(r'\/album\/[^\/]+\/(\d+)', url)
    if m:
      api_url = 'https://api.music.apple.com/v1/catalog/us/albums?ids={}&include=artists'.format(m.group(1))

  if not api_url:
    logger.warning('unable to parse id from ' + url)
    return None
  api_json = get_apple_data(api_url, url, save_debug)
  if not api_json:
    return None
  if save_debug:
    utils.write_file(api_json, './debug/apple.json')

  api_data = api_json['data'][0]
  if api_data['type'] == 'playlists':
    byline = api_data['attributes']['curatorName']
    list_title = 'Tracks'
    list_items = api_data['relationships']['tracks']['data']
    dt = datetime.fromisoformat(api_data['attributes']['lastModifiedDate'].replace('Z', '+00:00'))
  elif api_data['type'] == 'podcasts':
    byline = api_data['attributes']['artistName']
    list_title = 'Episodes'
    list_items = api_data['relationships']['episodes']['data']
    # Use the date from the most recent episode
    dt = datetime.fromisoformat(api_data['relationships']['episodes']['data'][0]['attributes']['releaseDateTime'].replace('Z', '+00:00'))
  elif api_data['type'] == 'albums':
    byline = api_data['attributes']['artistName']
    list_title = 'Tracks'
    list_items = api_data['relationships']['tracks']['data']
    dt = datetime.fromisoformat(api_data['attributes']['releaseDate'])
  else:
    logger.warning('unknown playlist type {} in {}'.format(api_data['type'], api_url))
    return None

  item = {}
  item['id'] = api_data['id']
  item['url'] = api_data['attributes']['url']
  item['title'] = api_data['attributes']['name']

  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = byline
  if api_data['attributes'].get('genreNames'):
    item['tags'] = api_data['attributes']['genreNames'].copy()
  item['_image'] = api_data['attributes']['artwork']['url'].replace('{w}', '640').replace('{h}', '640').replace('{f}', 'jpg')
  if api_data['attributes'].get('description'):
    item['summary'] = api_data['attributes']['description']['standard']
  elif api_data['attributes'].get('editorialNotes'):
    item['summary'] = api_data['attributes']['editorialNotes']['standard']

  poster = api_data['attributes']['artwork']['url'].replace('{w}', '128').replace('{h}', '128').replace('{f}', 'jpg')
  desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}</small>'.format(api_data['attributes']['url'], api_data['attributes']['name'], byline)
  item['content_html'] = '<blockquote><div style="display:flex; align-items:center;"><a href="{}"><img style="margin-right:8px;" src="{}"/></a><span>{}</a></span></div>'.format(api_data['attributes']['url'], poster, desc)
  item['content_html'] += '<h4 style="margin-top:0; margin-bottom:0.5em;">{}:</h4>'.format(list_title)
  if api_data['type'] == 'playlists' or api_data['type'] == 'albums':
    item['content_html'] += '<ol>'

  if 'max' in args:
    i_max = int(args['max'])
  else:
    i_max = -1
  for i, li in enumerate(list_items):
    if i == i_max:
      item['content_html'] += '<a href="{}/content?url={}">View all {}</a><hr/>'.format(config.server, quote_plus(item['url']), list_title.lower())
      break

    if api_data['type'] == 'podcasts':
      dt = datetime.fromisoformat(li['attributes']['releaseDateTime'].replace('Z', '+00:00'))
      date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
      duration = []
      t = math.floor(li['attributes']['durationInMilliseconds'] / 3600000)
      if t >= 1:
        duration.append('{} hr'.format(t))
      t = math.ceil((li['attributes']['durationInMilliseconds'] - 3600000*t) / 60000)
      if t > 0:
        duration.append('{} min.'.format(t))
      item['content_html'] += '<small>{}</small><br/><a href="{}">{}</a><br/><small>{}</small><br/><a style="text-decoration:none;" href="{}">&#9658; Play</a>&nbsp;<small>{}</small><hr/>'.format(date, li['attributes']['url'], li['attributes']['name'], li['attributes']['description']['short'], li['attributes']['assetUrl'], ' , '.join(duration))

    elif api_data['type'] == 'playlists':
      item['content_html'] += '<li><a href="{}">{}</a> <small>by {}</small></li>'.format(li['attributes']['url'], li['attributes']['name'], li['attributes']['artistName'])

    elif api_data['type'] == 'albums':
      item['content_html'] += '<li><a href="{}">{}</a></li>'.format(li['attributes']['url'], li['attributes']['name'])

  if api_data['type'] == 'playlists' or api_data['type'] == 'albums':
    item['content_html'] += '</ol>'
  item['content_html'] += '</blockquote>'
  return item

def get_content(url, args, save_debug=False):
  if '/podcast/' in url or '/playlist/' in url or '/album' in url:
    return get_apple_playlist(url, args, save_debug)
  return None

def get_feed(args, save_debug=False):
  return None