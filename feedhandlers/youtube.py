import json, pytube, re
from pytube.cipher import Cipher
from urllib.parse import parse_qs, quote_plus

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def search(query, save_debug=False):
  search_html = utils.get_url_html(
    'https://www.youtube.com/results?search_query=' + quote_plus(query))
  if search_html:
    m = re.search(r'var ytInitialData = (.*});<\/script>', search_html)
    if m:
      search_json = json.loads(m.group(1))
      if save_debug:
        utils.write_file(search_json, './debug/search.json')
      contents = search_json['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
      for content in contents:
        if content.get('videoRenderer'):
          return content['videoRenderer']['videoId']
  logger.warning('unable to get Youtube search results for query "{}"'.format(query))
  return ''

def get_content(url, args, save_debug=False):
  yt_id = ''
  if 'watch' in url:
    # Watch url
    m = re.search(r'youtube(-nocookie)?\.com\/watch\?v=([a-zA-Z0-9_-]{11})', url)
    if m:
      yt_id = m.group(2)
  elif 'embed' in url:
    # Embed url
    m = re.search(r'youtube(-nocookie)?\.com\/embed\/([a-zA-Z0-9_-]{11})', url)
    if m:
      yt_id = m.group(2)
  elif 'youtu.be' in url:
    m = re.search(r'youtu\.be\/([a-zA-Z0-9_-]{11})', url)
    if m:
      yt_id = m.group(1)

  if not yt_id:
    logger.warning('unable to determine Youtube video id in ' + url)

  yt_html = utils.get_url_html('https://www.youtube.com/watch?v=' + yt_id)
  if not yt_html:
    return None
  if save_debug:
    utils.write_file(yt_html, './debug/debug.html')

  m = re.search(r'ytInitialPlayerResponse = (.+?);(<\/script>|var)', yt_html)
  if not m:
    logger.warning('unable to extract yt info from ' + url)
    return None

  if False:
    utils.write_file(m.group(1), './debug/debug.txt')

  yt_json = json.loads(m.group(1))
  if save_debug:
    utils.write_file(yt_json, './debug/debug.json')

  item = {}
  item['id'] = yt_id
  item['url'] = 'https://www.youtube.com/watch?v=' + yt_id
  item['title'] = yt_json['videoDetails']['title']

  item['author'] = {}
  item['author']['name'] = yt_json['videoDetails']['author']

  if yt_json['videoDetails'].get('keywords'):
    item['tags'] = yt_json['videoDetails']['keywords'].copy()

  image = utils.closest_dict(yt_json['videoDetails']['thumbnail']['thumbnails'], 'height', 1080)
  item['_image'] = image['url']

  item['summary'] = yt_json['videoDetails']['shortDescription']

  if yt_json['playabilityStatus']['status'] == 'LIVE_STREAM_OFFLINE':
    item['content_html'] = utils.add_image(item['_image'], yt_json['playabilityStatus']['reason'])
  else:
    if save_debug:
      utils.write_file(yt_json['streamingData'], './debug/video.json')

    streams = {}
    streams['_video'] = utils.closest_dict(yt_json['streamingData']['formats'], 'height', 480)
    streams['_audio'] = [stream for stream in yt_json['streamingData']['adaptiveFormats'] if stream['itag'] == 251][0]

    stream_url = ''
    for key, stream in streams.items():
      if stream.get('url'):
        item[key] = stream['url']
      elif stream.get('signatureCipher'):
        if save_debug:
          logger.debug('decoding signatureCipher for ' + url)
        cipher_url = parse_qs(stream['signatureCipher'])
        js_url = pytube.extract.js_url(yt_html)
        js = utils.get_url_html(js_url)
        cipher = Cipher(js=js)
        signature = cipher.get_signature(cipher_url['s'][0])
        item[key] = cipher_url['url'][0] + '&sig=' + signature
      else:
        logger.warning('unable to get the {} stream in {}'.format(key, url))

    item['content_html'] = ''
    if args and 'audio' in args and item.get('_audio'):
      item['content_html'] = '<center><audio controls><source src="{}"></audio'.format(item['_audio'])
    elif item.get('_video'):
      item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])

  # Format the summary
  summary_html = yt_json['videoDetails']['shortDescription'].replace('\n', ' <br /> ')
  def replace_link(matchobj):
    return '<a href="{0}">{0}</a>'.format(matchobj.group(0))
  summary_html = re.sub('https?:\/\/[^\s]+', replace_link, summary_html)
  item['content_html'] += '<p>{}</p>'.format(summary_html)
  return item

def get_feed(args, save_debug=False):
  n = 0
  items = []
  feed = rss.get_feed(args, save_debug)
  for feed_item in feed['items']:
    if save_debug:
      logger.debug('getting content for ' + feed_item['url'])
    item = get_content(feed_item['url'], args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed['items'] = items.copy()
  return feed