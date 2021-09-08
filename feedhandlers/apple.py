import math, re, requests
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_apple_data(api_url, save_debug=False):
  print('get_apple_data ' + api_url)
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
    logger.warning('unexpected status code {} getting preflight podcast info from {}'.format(preflight.status_code, embed_url))
    return ''

  headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Bearer eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IkRBSlcxUk8wNjIifQ.eyJpc3MiOiJFUk1UQTBBQjZNIiwiaWF0IjoxNjI4NTEwOTQ3LCJleHAiOjE2MzQ3MzE3NDcsIm9yaWdpbiI6WyJodHRwczovL2VtYmVkLnBvZGNhc3RzLmFwcGxlLmNvbSJdfQ.4hpyCflT_5hmcLsD2NpwXMaE9ZhznHcoK0T60XVj7bfeIwibz-fiUao_sH3p8WECcw5f-6v0pFN1VwvSr7klkw",
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
    logger.warning('unexpected status code {} getting request podcast info from {}'.format(r.status_code, embed_url))
    return ''

  r_json = r.json()
  if save_debug:
    utils.write_file(r_json, './debug/apple.json')
  return r_json

def get_apple_playlist(api_url, args, save_debug=False):
  api_json = get_apple_data(api_url)
  if not api_json:
    return None

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
  if api_data['attributes']['description'].get('standard'):
    item['summary'] = api_data['attributes']['description']['standard']

  poster = api_data['attributes']['artwork']['url'].replace('{w}', '128').replace('{h}', '128').replace('{f}', 'jpg')
  item['content_html'] = '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0; border-bottom: 1px solid black;"><a href="{}"><img style="display:block; border-top-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top; border-bottom: 1px solid black;"><h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}</small></td></tr><tr><td colspan="2">{}:<ol style="margin-top:0;">'.format(api_data['attributes']['url'], poster, api_data['attributes']['url'], api_data['attributes']['name'], byline, list_title)

  if 'max' in args:
    i_max = int(args['max'])
  else:
    i_max = -1
  for i, li in enumerate(list_items):
    if i == i_max:
      item['content_html'] += '</ol></td></tr><tr><td colspan="2" style="text-align:center;"><a href="{}/content?url={}">View full playlist</a></td></tr>'.format(config.server, quote_plus(item['url']))
      break
    if api_data['type'] == 'playlists':
      item['content_html'] += '<li><a href="{}">{}</a><br/><small>by {}</small></li>'.format(li['attributes']['url'], li['attributes']['name'], li['attributes']['artistName'])
    elif api_data['type'] == 'podcasts':
      dt = datetime.fromisoformat(li['attributes']['releaseDateTime'].replace('Z', '+00:00'))
      date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
      time = []
      t = math.floor(li['attributes']['durationInMilliseconds'] / 3600000)
      if t >= 1:
        time.append('{} hr'.format(t))
      t = math.ceil((li['attributes']['durationInMilliseconds'] - 3600000*t) / 60000)
      if t > 0:
        time.append('{} min.'.format(t))
      item['content_html'] += '<li><a style="text-decoration:none;" href="{}">&#9658;</a>&nbsp;<a href="{}">{}</a><br/><small>{}, {}</small></li>'.format(li['attributes']['assetUrl'], li['attributes']['url'], li['attributes']['name'], date, ' , '.join(time))

  if i != i_max:
    item['content_html'] += '</ol></td></tr>'
  item['content_html'] += '</table></center>'
  return item

def get_content(url, args, save_debug=False):
  if '/podcast/' in url:
    m = re.search(r'\/id(\d+)', url)
    if not m:
      logger.warning('unable to parse Apple podcast id from ' + url)
      return ''
    api_url = 'https://amp-api.podcasts.apple.com/v1/catalog/us/podcasts/{}?include=episodes'.format(m.group(1))
    return get_apple_playlist(api_url, args, save_debug)
  elif '/playlist/' in url:
    m = re.search(r'\/pl\.([0-9a-f]+)', url)
    if not m:
      logger.warning('unable to parse Apple playlist id from ' + url)
      return ''
    api_url = 'https://api.music.apple.com/v1/catalog/us/playlists?ids=pl.{}&include=curator'.format(m.group(1))
    return get_apple_playlist(api_url, args, save_debug)
  return None

def get_feed(args, save_debug=False):
  return None